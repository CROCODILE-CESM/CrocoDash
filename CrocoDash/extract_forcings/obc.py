"""OBC (Open Boundary Condition) forcing extraction for CrocoDash.

Three-phase pipeline per boundary:

1. GET    — download raw data, chunked by ``get_step`` (default: full range in
             one request). Chunk size is driven by data-provider constraints
             (API limits, download size). Each chunk is written as
             ``{boundary}_unprocessed.{start}_{end}.nc``.
2. REGRID — validate raw coverage from filenames, then open all raw files
             lazily and regrid in ``regrid_step``-sized slices. Chunk size is
             driven by memory and xESMF performance. GET and REGRID chunks are
             fully independent.
3. MERGE  — concatenate regridded chunks into ``forcing_obc_segment_NNN.nc``.

Each phase is idempotent: existing output files are detected and skipped,
so a failed run can be safely re-started.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import math
import pandas as pd
import regional_mom6 as rm6
import xarray as xr
from CrocoDash import logging
from CrocoDash.extract_forcings import utils
from CrocoDash.grid import Grid

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
    dataset_varnames,
    fill_method,
    kwargs,
):

    output_folder = Path(output_folder + f"_{seg_id:03d}_{proc_id:02d}")
    output_folder.mkdir(exist_ok=True)
    (output_folder / "weights").mkdir(exist_ok=True)

    regridders = None
    proc_regridded_files = []

    with xr.open_dataset(hgrid_path) as hgrid:
        for pair in chunk_pairs:
            chunk_dated_output, regridders = _regrid_one_chunk(
                pair[0],
                pair[1],
                boundary,
                raw_files,
                seg_id,
                hgrid,
                output_folder,
                dataset_varnames,
                fill_method,
                regridders,
                kwargs,
            )
            proc_regridded_files.append(chunk_dated_output)

    return proc_regridded_files

def _regrid_one_chunk(
    chunk_start_date,
    chunk_end_date,
    boundary,
    raw_files,
    seg_id,
    hgrid,
    output_folder,
    dataset_varnames,
    fill_method,
    regridders,
    kwargs,
):
    """Regrid one chunk so that it can be called by multiple processes at once.

    Each regrid_step slice is written to a temp file (required by the rm6
    interface), then removed after regridding.
    """

    # Keep only files related to this chunk
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

    start_str = chunk_start_date.strftime("%Y-%m-%d")
    end_str = chunk_end_date.strftime("%Y-%m-%d")

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

    # Opens chunk raw files lazily via open_mfdataset
    with xr.open_mfdataset(
        [str(f) for f in sorted(chunk_raw_files)],
        combine="nested",
        concat_dim="time",
        coords="minimal",
        parallel=False,
    ) as ds_full:

        tmp_file = output_folder / f"_tmp_{boundary}_{start_str}_{end_str}.nc"
        # Daily-mean products like GLORYS timestamp each day's value at noon, so
        # slice by date strings (pandas partial-string indexing treats the end
        # string as covering that whole calendar day) to include chunk_end's own
        # data point instead of a midnight-anchored datetime slice excluding it.
        ds_full.sel(time=slice(start_str, end_str)).to_netcdf(tmp_file)

    # Regridder weights are computed once per processor on the first chunk and reused.
    try:
        seg = rm6.segment(
            hgrid=hgrid,
            bathymetry_path=None,
            outfolder=output_folder,
            segment_name=f"segment_{seg_id:03d}",
            orientation=boundary,
            startdate=chunk_start_date,
            repeat_year_forcing=False,
        )
        seg.regrid_velocity_tracers(
            infile=tmp_file,
            varnames=dataset_varnames,
            arakawa_grid=None,
            rotational_method=rm6.rotation.RotationMethod.EXPAND_GRID,
            regridding_method="bilinear",
            fill_method=fill_method,
            regridders=regridders,
            calendar=dataset_varnames["mom6_calendar"],
            time_units=dataset_varnames["time_units"],
            **kwargs,
        )
        temp_path = output_folder / f"forcing_obc_segment_{seg_id:03d}.nc"
        os.rename(temp_path, dated_output)
    finally:
        tmp_file.unlink(missing_ok=True)

    return dated_output, seg.regridders

# ---------------------------------------------------------------------------
# Phase functions — one call per boundary
# ---------------------------------------------------------------------------


def _get_boundary(
    boundary: str,
    start_date: datetime,
    end_date: datetime,
    get_step_days,
    hgrid_path,
    output_dir,
    product_name: str,
    function_name: str,
    variables: list,
    extra_args: dict,
) -> list:
    """Download all raw data for one boundary, chunked by get_step_days."""
    output_dir = Path(output_dir)

    data_access_fn = utils.get_data_access_function(product_name, function_name)

    # Get the bounding box for the specified boundary from the hgrid
    with xr.open_dataset(hgrid_path) as hgrid:
        latlon = Grid.get_bounding_boxes(hgrid)[boundary]

    pairs = list(_make_date_pairs(start_date, end_date, get_step_days))

    # Spread work across processes. If no chunking is prescribed it falls back
    # to one processor.
    with ProcessPoolExecutor(max_workers=min(12, len(pairs))) as ex:
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
    fill_method,
) -> list:
    """Regrid all raw files for one boundary, sliced by regrid_step_days."""
    kwargs = {}
    if "calendar" in dataset_varnames:
        kwargs["calendar"] = dataset_varnames["calendar"]
        kwargs["time_units"] = dataset_varnames["time_units"]

    pairs = list(_make_date_pairs(start_date, end_date, regrid_step_days))
    # Spread work across processes. If no chunking is prescribed it falls back
    # to one processor.

    num_workers = min(12, len(pairs))
    pairs_per_workers = math.ceil(len(pairs)/num_workers)
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
                dataset_varnames,
                fill_method,
                kwargs
            )
            for proc_id, chunk_pairs in enumerate(
                    [pairs[j : j + pairs_per_workers] for j in range(0, len(pairs), pairs_per_workers)]
            )
        ]
        for f in as_completed(futures):
            regridded_files.extend(
                f.result()
            )

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
    ds.to_netcdf(output_path)
    ds.close()
    logger.info(f"Saved merged boundary at {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def process_obc_conditions(
    start_date,
    end_date,
    boundary_number_conversion: dict,
    product_name: str,
    function_name: str,
    product_info: dict,
    hgrid_path,
    raw_dataset_path,
    regridded_dataset_path,
    output_path,
    get_step_days=None,
    regrid_step_days: int = 30,
    function_args: dict = None,
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
        boundary_number_conversion: Boundary name -> MOM6 segment number.
        product_name: Forcing data product name.
        function_name: Download function name for the product.
        product_info: Product variable-name metadata (a.k.a. dataset_varnames).
        hgrid_path: Path to the hgrid supergrid file.
        raw_dataset_path: Directory for raw downloaded data.
        regridded_dataset_path: Directory for per-chunk regridded data.
        output_path: Directory for final, merged MOM6-ready output files.
        get_step_days: GET chunk size in days; None = full range in one request.
        regrid_step_days: REGRID chunk size in days.
        function_args: Overrides for the access function's non-required
            arguments (e.g. `member`), as resolved by
            configure_forcings()'s function_overrides.
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

    variables, extra_args = utils.build_forcing_request(product_info, function_args)

    if product_info.get("boundary_fill_method", "regional_mom6") != "regional_mom6":
        raise ValueError(
            f"fill_method '{product_info['boundary_fill_method']}' is not supported."
        )
    fill_method = rm6.regridding.fill_missing_data

    raw_path.mkdir(exist_ok=True)
    regridded_path.mkdir(exist_ok=True)
    output_path.mkdir(exist_ok=True)

    for boundary in boundaries:
        seg_id = boundary_number_conversion[boundary]

        logger.info("GET [%s]: %s → %s", boundary, start_date.date(), end_date.date())
        _get_boundary(
            boundary=boundary,
            start_date=start_date,
            end_date=end_date,
            get_step_days=get_step_days,
            hgrid_path=str(hgrid_path),
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

        logger.info("REGRID [%s]: %d-day slices", boundary, regrid_step_days)
        regridded_files_by_boundary[boundary] = _regrid_boundary(
            boundary=boundary,
            seg_id=seg_id,
            raw_files=raw_files,
            start_date=start_date,
            end_date=end_date,
            regrid_step_days=regrid_step_days,
            hgrid_path=str(hgrid_path),
            output_folder=str(regridded_path),
            dataset_varnames=product_info,
            fill_method=fill_method,
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
