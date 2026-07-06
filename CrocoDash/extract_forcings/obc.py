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

import pandas as pd
import regional_mom6 as rm6
import xarray as xr
from CrocoDash import logging
from CrocoDash.extract_forcings import utils
from CrocoDash.grid import Grid
from CrocoDash.raw_data_access.registry import ProductRegistry

logger = logging.setup_logger(__name__)

_NETCDF_MAGIC = (b"\x89HDF", b"CDF\x01", b"CDF\x02")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_netcdf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        return any(header.startswith(m) for m in _NETCDF_MAGIC)
    except OSError:
        return False


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

    for chunk_start, chunk_end in _make_date_pairs(start_date, end_date, get_step_days):
        start_str = chunk_start.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")
        output_file = output_dir / f"{boundary}_unprocessed.{start_str}_{end_str}.nc"

        if output_file.exists():
            if not _is_valid_netcdf(output_file):
                raise RuntimeError(
                    f"OBC file {output_file} exists but is not valid NetCDF. "
                    "Delete it and re-run."
                )
            logger.info(f"OBC file {output_file.name} already exists. Skipping.")
            continue

        ProductRegistry.load()
        data_access_fn = ProductRegistry.get_access_function(
            product_name, function_name
        )
        hgrid = xr.open_dataset(hgrid_path)
        latlon = Grid.get_bounding_boxes_of_rectangular_grid(hgrid)[boundary]

        data_access_fn(
            dates=[start_str, end_str],
            lat_min=latlon["lat_min"],
            lat_max=latlon["lat_max"],
            lon_min=latlon["lon_min"],
            lon_max=latlon["lon_max"],
            output_folder=output_dir,
            output_filename=output_file.name,
            variables=variables,
            **extra_args,
        )


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
    """Regrid all raw files for one boundary, sliced by regrid_step_days.

    Opens raw files lazily via open_mfdataset, independent of how GET chunked
    them. Regridder weights are computed once on the first chunk and reused.
    Each regrid_step slice is written to a temp file (required by the rm6
    interface), then removed after regridding.
    """
    output_folder = Path(output_folder)
    (output_folder / "weights").mkdir(exist_ok=True)

    ds_full = xr.open_mfdataset(
        [str(f) for f in sorted(raw_files)],
        combine="nested",
        concat_dim="time",
        coords="minimal",
        parallel=False,
    )

    regridders = None
    regridded_files = []

    kwargs = {}
    if "calendar" in dataset_varnames:
        kwargs["calendar"] = dataset_varnames["calendar"]
        kwargs["time_units"] = dataset_varnames["time_units"]

    for chunk_start, chunk_end in _make_date_pairs(
        start_date, end_date, regrid_step_days
    ):
        start_str = chunk_start.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")
        dated_output = (
            output_folder / f"forcing_obc_segment_{seg_id:03d}_{start_str}_{end_str}.nc"
        )

        if dated_output.exists():
            if not _is_valid_netcdf(dated_output):
                raise RuntimeError(
                    f"Regridded file {dated_output} exists but is not valid NetCDF. "
                    "Delete it and re-run."
                )
            logger.info(f"Regridded file {dated_output.name} already exists. Skipping.")
            regridded_files.append(dated_output)
            continue

        tmp_file = output_folder / f"_tmp_{boundary}_{start_str}_{end_str}.nc"
        ds_full.sel(time=slice(chunk_start, chunk_end)).to_netcdf(tmp_file)

        try:
            hgrid = xr.open_dataset(hgrid_path)
            seg = rm6.segment(
                hgrid=hgrid,
                bathymetry_path=None,
                outfolder=output_folder,
                segment_name=f"segment_{seg_id:03d}",
                orientation=boundary,
                startdate=chunk_start,
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
                **kwargs,
            )
            regridders = seg.regridders
            temp_path = output_folder / f"forcing_obc_segment_{seg_id:03d}.nc"
            os.rename(temp_path, dated_output)
        finally:
            tmp_file.unlink(missing_ok=True)

        logger.info(f"Saved regridded file as {dated_output.name}")
        regridded_files.append(dated_output)

    ds_full.close()
    return regridded_files


def _merge_boundary(boundary_label: str, regridded_files: list, output_folder) -> Path:
    """Merge all regridded chunks for one boundary into the final forcing file."""
    output_folder = Path(output_folder)
    output_path = output_folder / f"forcing_obc_segment_{boundary_label}.nc"

    if output_path.exists():
        if not _is_valid_netcdf(output_path):
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


def process_obc_conditions(config_path, preview: bool = False):
    """Process boundary conditions through the GET → REGRID → MERGE pipeline.

    Each phase is idempotent. Re-running after a partial failure resumes from
    the last completed file.

    GET and REGRID chunk sizes (``get_step`` / ``regrid_step`` in config) are
    independent. GET defaults to the full date range in one request; REGRID
    defaults to 30-day slices for memory efficiency.

    Args:
        config_path: Path to the config JSON file.
        preview:     If True, return a dict of expected date pairs without
                     executing any downloads or regridding.
    """
    config = utils.Config(config_path)

    start_date = pd.to_datetime(config["basic"]["dates"]["start"]).to_pydatetime()
    end_date = pd.to_datetime(config["basic"]["dates"]["end"]).to_pydatetime()

    general = config["basic"]["general"]
    bnc = general["boundary_number_conversion"]
    # get_step=None → full range in one request; fall back to legacy "step" key
    get_step_days = general.get("get_step", None)
    regrid_step_days = int(general.get("regrid_step", general.get("step", 30)))

    product_name = config["basic"]["forcing"]["product_name"]
    function_name = config["basic"]["forcing"]["function_name"]
    product_info = config["basic"]["forcing"]["information"]
    raw_path = Path(config["basic"]["paths"]["raw_dataset_path"])
    regridded_path = Path(config["basic"]["paths"]["regridded_dataset_path"])
    output_path = Path(config["basic"]["paths"]["output_path"])
    hgrid_path = config["basic"]["paths"]["hgrid_path"]
    boundaries = list(bnc.keys())

    if preview:
        return {
            "boundaries": boundaries,
            "get_pairs": _make_date_pairs(start_date, end_date, get_step_days),
            "regrid_pairs": _make_date_pairs(start_date, end_date, regrid_step_days),
        }

    phys_vars = [
        product_info["u_var_name"],
        product_info["v_var_name"],
        product_info["eta_var_name"],
        product_info["tracer_var_names"]["temp"],
        product_info["tracer_var_names"]["salt"],
    ]
    extra_tracers = [
        v
        for k, v in product_info["tracer_var_names"].items()
        if k not in ("temp", "salt")
    ]
    variables = phys_vars + extra_tracers
    extra_args = {
        k: product_info[k]
        for k in ("dataset_path", "date_format", "regex", "delimiter")
        if k in product_info
    }

    if product_info.get("boundary_fill_method", "regional_mom6") != "regional_mom6":
        raise ValueError(
            f"fill_method '{product_info['boundary_fill_method']}' is not supported."
        )
    fill_method = rm6.regridding.fill_missing_data

    raw_path.mkdir(exist_ok=True)
    regridded_path.mkdir(exist_ok=True)
    output_path.mkdir(exist_ok=True)

    for boundary in boundaries:
        seg_id = bnc[boundary]

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
        seg_id = bnc[boundary]
        raw_files = _validate_coverage(
            sorted(raw_path.glob(f"{boundary}_unprocessed.*.nc")),
            lambda f: _parse_raw_filename_dates(f, boundary),
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
        seg_id = bnc[boundary]
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
