"""OBC (Open Boundary Condition) forcing extraction engine for CrocoDash.

Model-agnostic: this module gets raw data and chunks/merges it, but knows
nothing about how to regrid it. Callers (``mom6.py``, ``cice.py``, ``ww3.py``)
supply a ``regrid_chunk_fn`` that turns one raw chunk into that target's own
per-segment output file -- everything else (GET, date-chunking, idempotency,
MERGE) is shared.

Three-phase pipeline per boundary:

1. GET    — download raw data, chunked by ``get_step`` (default: full range in
             one request). Chunk size is driven by data-provider constraints
             (API limits, download size). Each chunk is written as
             ``{boundary}_unprocessed.{start}_{end}.nc``.
2. REGRID — validate raw coverage from filenames, then open all raw files
             lazily and regrid (via the caller-supplied ``regrid_chunk_fn``) in
             ``regrid_step``-sized slices. Chunk size is driven by memory and
             xESMF performance. GET and REGRID chunks are fully independent.
3. MERGE  — concatenate regridded chunks into ``forcing_obc_segment_NNN.nc``.

GET and REGRID phase automatically switch to multiprocessing when chunking and
multiple cpus are available.

Each phase is idempotent: existing output files are detected and skipped,
so a failed run can be safely re-started.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import math
import dask
import pandas as pd
import xarray as xr
from CrocoDash import logging
from CrocoDash.extract_forcings import utils
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo

logger = logging.setup_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_date_pairs(start: datetime, end: datetime, step_days):
    """Return non-overlapping (chunk_start, chunk_end) pairs covering [start, end].

    step_days=None returns a single pair spanning the full range.
    """
    if step_days is None:
        return [(start, end)]
    pairs = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=int(step_days) - 1), end)
        pairs.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return pairs


def _ocean_bbox_for_boundary(hgrid, supergridmask, boundary: str) -> dict:
    """Return a lat/lon bounding box covering only the ocean cells on a boundary edge.

    Uses supergridmask (shape ny×nx) to exclude land cells, giving a tighter download bbox
    than the full supergrid extent. Falls back to the full edge extent if all cells
    are land.
    """
    # T-cell centers are at every other supergrid node starting at index 1
    cell_lon = hgrid.x.values
    cell_lat = hgrid.y.values

    supergridmask_arr = (
        supergridmask.values.astype(bool)
        if hasattr(supergridmask, "values")
        else supergridmask.astype(bool)
    )

    if boundary == "north":
        edge_lon, edge_lat, mask = (
            cell_lon[-1, :],
            cell_lat[-1, :],
            supergridmask_arr[-1, :],
        )
    elif boundary == "south":
        edge_lon, edge_lat, mask = (
            cell_lon[0, :],
            cell_lat[0, :],
            supergridmask_arr[0, :],
        )
    elif boundary == "east":
        edge_lon, edge_lat, mask = (
            cell_lon[:, -1],
            cell_lat[:, -1],
            supergridmask_arr[:, -1],
        )
    elif boundary == "west":
        edge_lon, edge_lat, mask = (
            cell_lon[:, 0],
            cell_lat[:, 0],
            supergridmask_arr[:, 0],
        )
    else:
        raise ValueError(f"Unknown boundary '{boundary}'")

    ocean_lon = edge_lon[mask] if mask.any() else edge_lon
    ocean_lat = edge_lat[mask] if mask.any() else edge_lat

    return {
        "lat_min": float(ocean_lat.min()),
        "lat_max": float(ocean_lat.max()),
        "lon_min": float(ocean_lon.min()),
        "lon_max": float(ocean_lon.max()),
    }


def _parse_raw_filename_dates(path: Path, boundary: str):
    """Parse (start_date, end_date) from a raw OBC filename.

    Expects ISO dates (YYYY-MM-DD) separated by ``_``, e.g.
    ``east_unprocessed.2020-01-01_2020-01-31.nc``.
    """
    date_part = path.stem.removeprefix(f"{boundary}_unprocessed.")
    start_str, end_str = date_part.split("_")
    return datetime.fromisoformat(start_str), datetime.fromisoformat(end_str)


def _parse_regridded_filename_dates(path: Path, seg_id: int):
    """Parse (start_date, end_date) from a regridded OBC filename.

    Expects ISO dates (YYYY-MM-DD) separated by ``_``, e.g.
    ``forcing_obc_segment_001_2020-01-01_2020-01-05.nc``.
    """
    prefix = f"forcing_obc_segment_{seg_id:03d}_"
    date_part = path.stem.removeprefix(prefix)
    start_str, end_str = date_part.split("_")
    return datetime.fromisoformat(start_str), datetime.fromisoformat(end_str)


def _files_within_range(
    files: list, parse_dates, start_date: datetime, end_date: datetime
) -> list:
    """Keep only files whose filename date range falls within [start_date, end_date].

    raw_dataset_path is reused across runs, so a directory can accumulate files
    from a previous run with a different date range. Filtering here keeps
    _validate_coverage focused on the current request instead of erroring out
    on unrelated leftover files.
    """
    return [
        f
        for f in files
        if start_date <= parse_dates(f)[0] and parse_dates(f)[1] <= end_date
    ]


def _validate_coverage(
    files: list,
    parse_dates,
    label: str,
    start_date: datetime,
    end_date: datetime,
):
    """Check that files cover [start_date, end_date] without gaps or overlaps.

    parse_dates: callable(Path) -> (start_datetime, end_datetime)
    label: string used in error messages (e.g. boundary name or "segment 001")

    Reads dates from filenames only — does not open any files.

    Returns the sorted list of file paths on success.
    Raises FileNotFoundError if empty, or ValueError for gaps/overlaps/wrong endpoints.
    """
    if not files:
        raise FileNotFoundError(
            f"No files for [{label}] — preceding phase produced no output."
        )

    intervals = sorted(
        [(parse_dates(f), f) for f in files],
        key=lambda x: x[0][0],
    )

    first_start = intervals[0][0][0]
    last_end = intervals[-1][0][1]

    if first_start != start_date:
        raise ValueError(
            f"[{label}] Coverage starts {first_start:%Y-%m-%d}, "
            f"expected {start_date:%Y-%m-%d}"
        )
    if last_end != end_date:
        raise ValueError(
            f"[{label}] Coverage ends {last_end:%Y-%m-%d}, "
            f"expected {end_date:%Y-%m-%d}"
        )

    for i in range(len(intervals) - 1):
        cur_end = intervals[i][0][1]
        next_start = intervals[i + 1][0][0]
        expected = cur_end + timedelta(days=1)
        if next_start < expected:
            raise ValueError(f"[{label}] Overlapping files around {cur_end:%Y-%m-%d}")
        if next_start > expected:
            raise ValueError(
                f"[{label}] Gap in coverage: {cur_end:%Y-%m-%d} → {next_start:%Y-%m-%d}"
            )

    return [f for _, f in intervals]


def _get_one_chunk(
    chunk_start: datetime,
    chunk_end: datetime,
    boundary: str,
    product_name: str,
    function_name: str,
    latlon: dict,
    output_dir: str | Path,
    variables: list,
    extra_args: dict,
):
    """Download one chunk so that it can be called by multiple processes at once."""

    start_str = chunk_start.strftime("%Y-%m-%d")
    end_str = chunk_end.strftime("%Y-%m-%d")
    output_filename = f"{boundary}_unprocessed.{start_str}_{end_str}.nc"
    data_access_fn = utils.get_data_access_function(product_name, function_name)

    return utils.fetch_raw_chunk(
        data_access_fn=data_access_fn,
        dates=[start_str, end_str],
        latlon=latlon,
        name=boundary,
        output_folder=output_dir,
        output_filename=output_filename,
        variables=variables,
        extra_args=extra_args,
    )


def _regrid_per_process(
    proc_id,
    chunk_pairs,
    boundary,
    raw_files,
    seg_id,
    hgrid_path,
    output_folder,
    scratch_folder,
    dataset_varnames,
    regrid_chunk_fn,
    start_date,
):
    """Regrid this worker's slice of the chunk list.

    Runs in its own process, so it opens its own hgrid and keeps its own
    regridder cache -- ESMF weights are computed on this worker's first chunk
    and reused for the rest of its slice. ``scratch_folder`` is where
    ``regrid_chunk_fn`` is pointed: it writes to the fixed filename
    ``forcing_obc_segment_{seg_id:03d}.nc``, so concurrent workers need
    separate folders or they would overwrite each other. Finished chunks are
    moved into ``output_folder`` under their dated name, so the on-disk result
    does not depend on how many workers ran.
    """
    output_folder = Path(output_folder)
    scratch_folder = Path(scratch_folder)
    scratch_folder.mkdir(parents=True, exist_ok=True)
    (scratch_folder / "weights").mkdir(exist_ok=True)

    logger.info("PROC [%d] - REGRID [%s]: Spun up new proc", proc_id, boundary)

    regridders = None
    proc_regridded_files = []

    with xr.open_dataset(hgrid_path) as hgrid:
        for chunk_start, chunk_end in chunk_pairs:
            chunk_dated_output, regridders = _regrid_one_chunk(
                proc_id,
                chunk_start,
                chunk_end,
                boundary,
                raw_files,
                seg_id,
                hgrid,
                output_folder,
                scratch_folder,
                dataset_varnames,
                regrid_chunk_fn,
                regridders,
                start_date,
            )
            proc_regridded_files.append(chunk_dated_output)

    return proc_regridded_files


def _regrid_one_chunk(
    proc_id,
    chunk_start_date,
    chunk_end_date,
    boundary,
    raw_files,
    seg_id,
    hgrid,
    output_folder,
    scratch_folder,
    dataset_varnames,
    regrid_chunk_fn,
    regridders,
    start_date,
):
    """Regrid one chunk so that it can be called by multiple processes at once.

    Only the raw files overlapping this chunk are opened, so each worker holds
    its own small slice rather than the whole boundary. The chunk is handed to
    ``regrid_chunk_fn`` as an in-memory ``xr.Dataset`` -- if that target's
    regrid step needs a file on disk (as regional_mom6's does), writing and
    cleaning it up is its own business, not this engine's.
    """
    start_str = chunk_start_date.strftime("%Y-%m-%d")
    end_str = chunk_end_date.strftime("%Y-%m-%d")
    logger.info(
        "PROC [%d] - REGRID [%s]: Chunk start - end date: [%s] - [%s]",
        proc_id,
        boundary,
        start_str,
        end_str,
    )

    dated_output = (
        output_folder / f"forcing_obc_segment_{seg_id:03d}_{start_str}_{end_str}.nc"
    )
    if dated_output.exists():
        if not utils.is_valid_netcdf(dated_output):
            raise RuntimeError(
                f"Regridded file {dated_output} exists but is not valid NetCDF. "
                "Delete it and re-run."
            )
        logger.info(f"Regridded file {dated_output.name} already exists. Skipping.")
        return dated_output, regridders

    logger.info("PROC [%d] - REGRID [%s]: Validating coverage", proc_id, boundary)
    parse_raw_dates = lambda f, boundary=boundary: _parse_raw_filename_dates(
        f, boundary
    )
    chunk_raw_files = _validate_coverage(
        _files_within_range(
            sorted(raw_files),
            parse_raw_dates,
            chunk_start_date,
            chunk_end_date,
        ),
        parse_raw_dates,
        boundary,
        chunk_start_date,
        chunk_end_date,
    )

    logger.info("PROC [%d] - REGRID [%s]: Performing regrid", proc_id, boundary)
    with xr.open_mfdataset(
        [str(f) for f in sorted(chunk_raw_files)],
        combine="nested",
        concat_dim="time",
        coords="minimal",
        parallel=False,
    ) as ds_full:
        # Daily-mean products like GLORYS timestamp each day's value at noon, so
        # slice by date strings (pandas partial-string indexing treats the end
        # string as covering that whole calendar day) to include chunk_end's own
        # data point instead of a midnight-anchored datetime slice excluding it.
        chunk_ds = ds_full.sel(time=slice(start_str, end_str))

        regridders = regrid_chunk_fn(
            ds=chunk_ds,
            hgrid=hgrid,
            boundary=boundary,
            seg_id=seg_id,
            outfolder=scratch_folder,
            dataset_varnames=dataset_varnames,
            start_date=start_date,
            regridders=regridders,
        )

    os.replace(scratch_folder / f"forcing_obc_segment_{seg_id:03d}.nc", dated_output)

    logger.info(
        "PROC [%d] - REGRID [%s]: Regridding done for %s",
        proc_id,
        boundary,
        dated_output,
    )
    return dated_output, regridders


def available_cpus():
    """Get number of available processes to spun"""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        # Fallback for systems without sched_getaffinity
        return 12


# ---------------------------------------------------------------------------
# Phase functions — one call per boundary
# ---------------------------------------------------------------------------


def _get_boundary(
    boundary: str,
    start_date: datetime,
    end_date: datetime,
    get_step_days,
    latlon: dict,
    output_dir,
    product_name: str,
    function_name: str,
    variables: list,
    extra_args: dict,
) -> list:
    """Download all raw data for one boundary, chunked by get_step_days."""
    output_dir = Path(output_dir)

    pairs = list(_make_date_pairs(start_date, end_date, get_step_days))

    # Spread work across processes. If no chunking is prescribed it falls back
    # to one processor. For get_glorys_data_script_for_cli(), generate CLI
    # script that runs serially
    if function_name == "get_glorys_data_script_for_cli":
        for chunk_start, chunk_end in pairs:
            start_str = chunk_start.strftime("%Y-%m-%d")
            end_str = chunk_end.strftime("%Y-%m-%d")
            output_filename = f"{boundary}_unprocessed.{start_str}_{end_str}.nc"
            data_access_fn = utils.get_data_access_function(product_name, function_name)

            utils.fetch_raw_chunk(
                data_access_fn=data_access_fn,
                dates=[start_str, end_str],
                latlon=latlon,
                name=boundary,
                output_folder=output_dir,
                output_filename=output_filename,
                variables=variables,
                extra_args=extra_args,
            )
    else:
        num_workers = min(available_cpus(), len(pairs))
        with ProcessPoolExecutor(max_workers=num_workers) as ex:
            futures = [
                ex.submit(
                    _get_one_chunk,
                    chunk_start,
                    chunk_end,
                    boundary,
                    product_name,
                    function_name,
                    latlon,
                    output_dir,
                    variables,
                    extra_args,
                )
                for chunk_start, chunk_end in pairs
            ]
            for f in as_completed(futures):
                f.result()


def _regrid_boundary(
    boundary: str,
    seg_id: int,
    raw_files: list,
    start_date: datetime,
    end_date: datetime,
    regrid_step_days: int,
    hgrid_path,
    output_folder,
    dataset_varnames: dict,
    regrid_chunk_fn,
) -> list:
    """Regrid all raw files for one boundary, sliced by regrid_step_days.

    Each regrid_step slice is handed to ``regrid_chunk_fn`` (the
    target-specific regrid step -- see ``mom6.py``/``cice.py``/``ww3.py``) as
    a plain in-memory ``xr.Dataset`` -- no file, no cleanup for this engine to
    manage. If a target's own regrid step needs a file on disk (as
    regional_mom6's does), that's its own business: write one, use it, remove
    it. ``regrid_chunk_fn`` is expected to write its output to
    ``<its outfolder> / f"forcing_obc_segment_{seg_id:03d}.nc"`` and return the
    updated regridder cache to reuse on the next chunk (regridder weights are
    typically computed once and reused).

    Chunks are spread across processes. Weight reuse is per worker, not global:
    each worker computes the regridder on its first chunk and reuses it for the
    rest of its own slice. One worker (the single-CPU case) is the plain
    sequential engine, regridding straight into ``output_folder``.
    """
    output_folder = Path(output_folder)
    (output_folder / "weights").mkdir(exist_ok=True)

    pairs = list(_make_date_pairs(start_date, end_date, regrid_step_days))
    if not pairs:
        return []

    num_workers = max(1, min(available_cpus(), len(pairs)))

    if num_workers == 1:
        return sorted(
            _regrid_per_process(
                0,
                pairs,
                boundary,
                raw_files,
                seg_id,
                hgrid_path,
                output_folder,
                output_folder,
                dataset_varnames,
                regrid_chunk_fn,
                start_date,
            ),
            key=os.path.basename,
        )

    per_worker = math.ceil(len(pairs) / num_workers)
    worker_slices = [
        pairs[j : j + per_worker] for j in range(0, len(pairs), per_worker)
    ]
    logger.info(
        "REGRID [%s]: %d chunks across %d processes",
        boundary,
        len(pairs),
        len(worker_slices),
    )

    regridded_files = []
    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        futures = [
            ex.submit(
                _regrid_per_process,
                proc_id,
                chunk_pairs,
                boundary,
                raw_files,
                seg_id,
                hgrid_path,
                output_folder,
                output_folder / f"_proc_{seg_id:03d}_{proc_id:02d}",
                dataset_varnames,
                regrid_chunk_fn,
                start_date,
            )
            for proc_id, chunk_pairs in enumerate(worker_slices)
        ]
        for f in as_completed(futures):
            regridded_files.extend(f.result())

    return sorted(regridded_files, key=os.path.basename)


def _merge_boundary(boundary_label: str, regridded_files: list, output_folder) -> Path:
    """Merge all regridded chunks for one boundary into the final forcing file."""
    output_folder = Path(output_folder)
    output_path = output_folder / f"forcing_obc_segment_{boundary_label}.nc"

    if output_path.exists():
        if not utils.is_valid_netcdf(output_path):
            raise RuntimeError(
                f"Merged OBC file {output_path} exists but is not valid NetCDF. "
                "Delete it and re-run."
            )
        logger.info(f"Merged file {output_path.name} already exists. Skipping.")
        return output_path

    ds = xr.open_mfdataset(
        [str(p) for p in regridded_files],
        combine="nested",
        concat_dim="time",
        coords="minimal",
        parallel=False,
    )
    # open_mfdataset makes this dask-backed, so the write is exposed to the
    # same intermittent HDF5/threaded-scheduler deadlock documented at
    # mom6.py's _regrid_obc_chunk. Not observed here -- guarded because it is
    # the identical pattern, and a deadlock that strikes one write in four is
    # not something to leave to chance two functions away from a known one.
    with dask.config.set(scheduler="synchronous"):
        ds.to_netcdf(output_path)
    ds.close()
    logger.info(f"Saved merged boundary at {output_path}")
    return output_path


def process_obc_conditions(
    start_date,
    end_date,
    boundary_number_conversion: dict,
    product_name: str,
    function_name: str,
    variables: list,
    extra_args: dict,
    dataset_varnames: dict,
    hgrid_path,
    raw_dataset_path,
    regridded_dataset_path,
    output_path,
    regrid_chunk_fn,
    get_step_days=None,
    regrid_step_days: int = 30,
    bathymetry_path=None,
    preview: bool = False,
):
    """Process boundary conditions through the GET → REGRID → MERGE pipeline.

    Each phase is idempotent. Re-running after a partial failure resumes from
    the last completed file.

    GET and REGRID chunk sizes are independent. GET defaults to the full date
    range in one request; REGRID defaults to 30-day slices for memory
    efficiency.

    Args:
        start_date: Forcing start date (datetime or any pandas-parseable string).
        end_date: Forcing end date (datetime or any pandas-parseable string).
        boundary_number_conversion: Boundary name -> target-model segment number.
        product_name: Forcing data product name.
        function_name: Download function name for the product.
        variables: Variable names to request from the download function
            (already resolved by the caller from its own product metadata).
        extra_args: Extra kwargs for the download function (already resolved
            by the caller).
        dataset_varnames: Opaque metadata dict forwarded to ``regrid_chunk_fn``
            -- this module never reads its keys itself.
        hgrid_path: Path to the hgrid supergrid file.
        raw_dataset_path: Directory for raw downloaded data.
        regridded_dataset_path: Directory for per-chunk regridded data.
        output_path: Directory for final, merged output files.
        regrid_chunk_fn: Target-specific regrid step -- see ``_regrid_boundary``.
        get_step_days: GET chunk size in days; None = full range in one request.
        regrid_step_days: REGRID chunk size in days.
        bathymetry_path: Optional path to the case's bathymetry file. When
            given, download bounding boxes are computed from the bathymetry
            ocean tmask (tighter than the full supergrid edge extent). When
            omitted, falls back to the full supergrid bounding box per
            boundary.
        preview: If True, return a dict of expected date pairs without
            executing any downloads or regridding.
    """
    start_date = pd.to_datetime(start_date).to_pydatetime()
    end_date = pd.to_datetime(end_date).to_pydatetime()

    raw_path = Path(raw_dataset_path)
    regridded_path = Path(regridded_dataset_path)
    output_path = Path(output_path)
    boundaries = list(boundary_number_conversion.keys())

    if preview:
        return {
            "boundaries": boundaries,
            "get_pairs": _make_date_pairs(start_date, end_date, get_step_days),
            "regrid_pairs": _make_date_pairs(start_date, end_date, regrid_step_days),
        }

    # Compute per-boundary download bboxes using the bathymetry tmask so we only
    # request data over ocean cells (tighter than the full supergrid edge extent).
    with xr.open_dataset(hgrid_path) as hgrid_ds:
        assert not Grid.is_cyclic_x(hgrid_ds), "bboxes not supported for cyclic grids."
        if bathymetry_path:
            grid_obj = Grid.from_supergrid(hgrid_path)
            with xr.open_dataset(bathymetry_path) as bds:
                min_depth = bds.attrs.get("min_depth", 0.0)
            topo = Topo.from_topo_file(
                grid=grid_obj,
                topo_file_path=bathymetry_path,
                min_depth=min_depth,
                git=False,
            )
            boundary_bboxes = {
                b: _ocean_bbox_for_boundary(hgrid_ds, topo.supergridmask, b)
                for b in boundaries
            }
            logger.info("Using tmask-derived bounding boxes for OBC data download.")
        else:
            full_bboxes = Grid.get_bounding_boxes(hgrid_ds)
            boundary_bboxes = {b: full_bboxes[b] for b in boundaries}
            logger.info(
                "No bathymetry_path given; using full supergrid bounding boxes."
            )

    raw_path.mkdir(exist_ok=True)
    regridded_path.mkdir(exist_ok=True)
    output_path.mkdir(exist_ok=True)

    for j, boundary in enumerate(boundaries):
        seg_id = boundary_number_conversion[boundary]

        logger.info("GET [%s]: %s → %s", boundary, start_date.date(), end_date.date())
        _get_boundary(
            boundary=boundary,
            start_date=start_date,
            end_date=end_date,
            get_step_days=get_step_days,
            latlon=boundary_bboxes[boundary],
            output_dir=str(raw_path),
            product_name=product_name,
            function_name=function_name,
            variables=variables,
            extra_args=extra_args,
        )

    regridded_files_by_boundary = {}
    for boundary in boundaries:
        seg_id = boundary_number_conversion[boundary]
        parse_raw_dates = lambda f, boundary=boundary: _parse_raw_filename_dates(
            f, boundary
        )
        raw_files = _validate_coverage(
            _files_within_range(
                sorted(raw_path.glob(f"{boundary}_unprocessed.*.nc")),
                parse_raw_dates,
                start_date,
                end_date,
            ),
            parse_raw_dates,
            boundary,
            start_date,
            end_date,
        )

        logger.info("REGRID [%s]: %s-day slices", boundary, regrid_step_days)
        regridded_files_by_boundary[boundary] = _regrid_boundary(
            boundary=boundary,
            seg_id=seg_id,
            raw_files=raw_files,
            start_date=start_date,
            end_date=end_date,
            regrid_step_days=regrid_step_days,
            hgrid_path=str(hgrid_path),
            output_folder=str(regridded_path),
            dataset_varnames=dataset_varnames,
            regrid_chunk_fn=regrid_chunk_fn,
        )

    for boundary in boundaries:
        seg_id = boundary_number_conversion[boundary]
        regridded_files = regridded_files_by_boundary[boundary]
        _validate_coverage(
            regridded_files,
            lambda f: _parse_regridded_filename_dates(f, seg_id),
            f"segment {seg_id:03d}",
            start_date,
            end_date,
        )

        logger.info("MERGE [%s]", boundary)
        _merge_boundary(
            boundary_label=f"{seg_id:03d}",
            regridded_files=regridded_files,
            output_folder=str(output_path),
        )

    logger.info("OBC processing complete.")
