"""
Data Access Module -> CESM ocean output

Two products, split because they have different variable/coordinate naming
conventions (and so need different MOM6ForcingProduct metadata):

- CESM_POP_OUTPUT: CESM-POP tseries output (CESM-HR FOSI, CESM2-LENS2)
- CESM_MOM_OUTPUT: native MOM6 output (e.g. parent-run history/diag_table
  output for nesting a child domain)

Both share the same lower-level file-discovery/subsetting helpers below.
"""

import xarray as xr
from pathlib import Path
from dateutil import parser
import os
import re
from datetime import datetime
from pathlib import Path
import xarray as xr
import cftime
import dask.base
import numpy as np
import pandas as pd

from CrocoDash.raw_data_access.base import *


class CESM_POP_OUTPUT(MOM6ForcingProduct):
    product_name = "cesm_pop_output"
    description = "CESM ocean output (POP2 grid) for use as IC and OBC, including CESM-HR FOSI and CESM2 Large Ensemble (LENS2)"
    link = "https://gdex.ucar.edu/datasets/d267000/"
    time_var_name = "time"
    boundary_fill_method = "regional_mom6"
    tracer_x_coord = "nlon"
    tracer_y_coord = "nlat"
    u_var_name = "UVEL"
    z_unit_conversion = 0.01
    v_var_name = "VVEL"
    u_x_coord = "nlon"
    u_y_coord = "nlat"
    v_x_coord = "nlon"
    v_y_coord = "nlat"
    u_lat_coord = "TLAT"
    u_lon_coord = "TLONG"
    v_lat_coord = "TLAT"
    v_lon_coord = "TLONG"
    tracer_lat_coord = "TLAT"
    tracer_lon_coord = "TLONG"
    eta_var_name = "SSH"
    time_units = "days since 1850-01-01"
    calendar = NOLEAP
    # The default dataset_path is tseries/month_1, monthly means; pass
    # data_freq for an archive of another cadence (e.g. "D" for day_1).
    time_sampling = TimeSampling("MS", "mean")
    depth_coord = ["z_t", "z_t_150m"]
    delimiter = "."
    tracer_var_names = {"temp": "TEMP", "salt": "SALT"}
    marbl_var_names = {
        "PO4": "PO4",
        "NO3": "NO3",
        "SiO3": "SiO3",
        "NH4": "NH4",
        "Fe": "Fe",
        "Lig": "Lig",
        "O2": "O2",
        "DIC": "DIC",
        "DIC_ALT_CO2": "DIC_ALT_CO2",
        "ALK": "ALK",
        "ALK_ALT_CO2": "ALK_ALT_CO2",
        "DOC": "DOC",
        "DON": "DON",
        "DOP": "DOP",
        "DOPr": "DOPr",
        "DONr": "DONr",
        "DOCr": "DOCr",
        "microzooC": "microzooC",
        "mesozooC": "mesozooC",
        "spChl": "spChl",
        "spC": "spC",
        "spP": "spP",
        "spFe": "spFe",
        "diatChl": "diatChl",
        "diatC": "diatC",
        "diatP": "diatP",
        "diatFe": "diatFe",
        "diatSi": "diatSi",
        "diazChl": "diazChl",
        "diazC": "diazC",
        "diazP": "diazP",
        "diazFe": "diazFe",
        "coccoChl": "coccoChl",
        "coccoC": "coccoC",
        "coccoP": "coccoP",
        "coccoFe": "coccoFe",
        "coccoCaCO3": "coccoCaCO3",
    }

    @classmethod
    def coverage(cls, method_name, **kwargs):
        return tseries_coverage(**kwargs)

    @accessmethod(
        subsample=True,
        data_freq=True,
        description=(
            "Gets CESM single-variable-per-file (tseries) ocean data from a given "
            "path (by default a POP-MARBL run) — the standard CESM postprocessed "
            "output organization, one variable per file series with the date range "
            "encoded in the filename. Covers both CESM-HR FOSI and CESM2-LENS2 "
            "(pass `member` to select an ensemble member)."
        ),
        type="python",
        how_to_use=(
            "Requires access to the `dataset_path` directory containing CESM "
            "single-variable tseries NetCDF files (POP variable/coordinate names). "
            "On GLADE, the default path points to a CESM-HR FOSI-BGC run. For "
            "CESM2-LENS2, pass `dataset_path='/gdex/data/d651056/CESM2-LE/ocn/proc/"
            "tseries/month_1'` and set `member` to the desired ensemble member "
            "(e.g. 'LE2-1001.001')."
        ),
    )
    def get_cesm_single_variable_data(
        when,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename=None,
        variables=["SSH", "TEMP", "SALT", "VVEL", "UVEL"],
        dataset_path="/glade/campaign/collections/cmip/CMIP6/CESM-HR/FOSI_BGC/HR/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001/ocn/proc/tseries/month_1",
        member=None,
        date_format: str = "%Y%m%d",
        regex=r"(\d{6,8})-(\d{6,8})",
        delimiter=".",
        lat_name="TLAT",
        lon_name="TLONG",
        preview=False,
        data_freq=None,
    ):
        resolve_time_sampling(
            CESM_POP_OUTPUT, "get_cesm_single_variable_data", data_freq
        )
        return read_single_variable_tseries_data(
            when,
            lat_min,
            lat_max,
            lon_min,
            lon_max,
            output_folder,
            output_filename,
            variables,
            dataset_path,
            member,
            date_format,
            regex,
            delimiter,
            lat_name,
            lon_name,
            preview,
            data_freq=data_freq or CESM_POP_OUTPUT.time_sampling.frequency,
        )


class CESM_MOM_OUTPUT(MOM6ForcingProduct):
    product_name = "cesm_mom_output"
    description = (
        "Native MOM6 output (full history/diagnostic files, or diag_table-"
        "extracted cross-section slices) for use as IC/OBC forcing - e.g. for "
        "nesting a child domain inside an outer/parent MOM6 run."
    )
    link = "https://mom6.readthedocs.io/en/main/api/generated/pages/Diagnostics.html"
    time_var_name = "time"
    time_units = "days"
    boundary_fill_method = "regional_mom6"
    tracer_x_coord = "xh"
    tracer_y_coord = "yh"
    tracer_lon_coord = "xh"
    tracer_lat_coord = "yh"
    u_var_name = "uo"
    u_x_coord = "xq"
    u_y_coord = "yh"
    u_lon_coord = "xq"
    u_lat_coord = "yh"
    v_var_name = "vo"
    v_x_coord = "xh"
    v_y_coord = "yq"
    v_lon_coord = "xh"
    v_lat_coord = "yq"
    eta_var_name = "zos"
    depth_coord = "z_l"
    calendar = NOLEAP
    # The cadence is whatever the dataset_path given holds, so it can't be
    # declared here.
    time_sampling = USER_SPECIFIED
    tracer_var_names = {"temp": "thetao", "salt": "so"}

    @classmethod
    def coverage(cls, method_name, **kwargs):
        # Only the tseries reader has the dates in its file names.
        if method_name != "get_mom6_single_variable_data":
            return super().coverage(method_name, **kwargs)
        return tseries_coverage(**kwargs)

    @accessmethod(
        subsample=True,
        data_freq=True,
        description=(
            "Reads native MOM6 output (full history/diagnostic files, or "
            "diag_table-extracted cross-section slices) from any directory and "
            "subsets to a lat/lon bounding box — e.g. for nesting a child domain "
            "inside an outer/parent MOM6 run."
        ),
        type="python",
        how_to_use=(
            "Point dataset_path at any directory of MOM6 output NetCDF files (a "
            "parent run's history dir, or diag_table-extracted region slices). "
            "Narrow which files are read with file_glob, e.g. "
            "'*.ocean_month_z*.nc' for full history, or "
            "'<case_prefix>.<region_name>*.nc' for a nesting cross-section."
        ),
    )
    def get_mom6_output_data(
        when,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename=None,
        variables=["zos", "thetao", "so", "uo", "vo"],
        dataset_path=None,
        file_glob="*.nc",
        time_var_name="time",
        buffer_deg=1.5,
        preview=False,
        data_freq=None,
    ):
        resolve_time_sampling(CESM_MOM_OUTPUT, "get_mom6_output_data", data_freq)
        validate_dataset_path(dataset_path)

        files = sorted(Path(dataset_path).glob(file_glob))
        if not files:
            raise FileNotFoundError(
                f"No files matching glob '{file_glob}' found in {dataset_path}."
            )

        ds = xr.open_mfdataset(files, combine="by_coords")
        ds = date_means_at_interval_start(ds, time_var_name)
        check_data_freq(ds, data_freq, time_var_name, dataset_path)
        ds = when.select(ds, time_var_name)
        ds = convert_cftime_to_numeric(
            ds, time_var_name=time_var_name, calendar=CESM_MOM_OUTPUT.calendar
        )
        keep_vars = [v for v in variables if v in ds.data_vars]
        missing_vars = [v for v in variables if v not in ds.data_vars]
        if missing_vars:
            CESM_MOM_OUTPUT.logger.warning(
                f"Requested variables not found in {dataset_path} (glob '{file_glob}'): "
                f"{missing_vars}"
            )
        ds = ds[keep_vars]

        # MOM6's C-grid staggers uo/vo onto different horizontal dims than the
        # tracer grid (xq for u-points, yq for v-points). A single tracer-grid
        # mask broadcast across the whole dataset (ds.where(mask, drop=True))
        # would add the tracer dims to those variables instead of subsetting
        # them, since xarray broadcasts unmatched dims by name. Build one mask
        # per C-grid point - tracer, u, v - and apply each only to the
        # variables living on that point.
        grid_points = {
            (CESM_MOM_OUTPUT.tracer_y_coord, CESM_MOM_OUTPUT.tracer_x_coord),
            (CESM_MOM_OUTPUT.u_y_coord, CESM_MOM_OUTPUT.u_x_coord),
            (CESM_MOM_OUTPUT.v_y_coord, CESM_MOM_OUTPUT.v_x_coord),
        }
        subsets = []
        for y_dim, x_dim in grid_points:
            if y_dim not in ds.dims or x_dim not in ds.dims:
                continue
            grid_vars = [
                v for v in ds.data_vars if y_dim in ds[v].dims and x_dim in ds[v].dims
            ]
            if not grid_vars:
                continue
            mask = bbox_mask(
                ds, lat_min, lat_max, lon_min, lon_max, y_dim, x_dim, buffer_deg
            )
            subsets.append(ds[grid_vars].where(mask, drop=True))
        ds = xr.merge(subsets)

        if preview:
            return ds
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        if output_filename is None:
            output_filename = (
                f"mom6_output_subset_{lat_min}_{lat_max}_{lon_min}_{lon_max}.nc"
            )
        output_path = output_folder / output_filename
        ds.load().to_netcdf(output_path)
        return [output_path]

    @accessmethod(
        subsample=True,
        data_freq=True,
        description=(
            "Gets native MOM6 output that's organized in the CESM single-"
            "variable-per-file (tseries) convention instead of one multi-"
            "variable file per region/timestep — some parent runs post-process "
            "their history output this way before archiving it."
        ),
        type="python",
        how_to_use=(
            "Requires access to a `dataset_path` directory containing MOM6 "
            "tseries NetCDF files (one variable per file series, MOM6 native "
            "variable/coordinate names, date range encoded in the filename)."
        ),
    )
    def get_mom6_single_variable_data(
        when,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename=None,
        variables=["zos", "thetao", "so", "uo", "vo"],
        dataset_path=None,
        member=None,
        date_format: str = "%Y%m%d",
        regex=r"(\d{6,8})-(\d{6,8})",
        delimiter=".",
        preview=False,
        data_freq=None,
    ):
        resolve_time_sampling(
            CESM_MOM_OUTPUT, "get_mom6_single_variable_data", data_freq
        )
        return read_single_variable_tseries_data(
            when,
            lat_min,
            lat_max,
            lon_min,
            lon_max,
            output_folder,
            output_filename,
            variables,
            dataset_path,
            member,
            date_format,
            regex,
            delimiter,
            CESM_MOM_OUTPUT.tracer_y_coord,
            CESM_MOM_OUTPUT.tracer_x_coord,
            preview,
            data_freq=data_freq,
            grid_coords={
                CESM_MOM_OUTPUT.u_var_name: (
                    CESM_MOM_OUTPUT.u_y_coord,
                    CESM_MOM_OUTPUT.u_x_coord,
                ),
                CESM_MOM_OUTPUT.v_var_name: (
                    CESM_MOM_OUTPUT.v_y_coord,
                    CESM_MOM_OUTPUT.v_x_coord,
                ),
            },
        )


def validate_dataset_path(dataset_path):
    if dataset_path is None or not Path(dataset_path).exists():
        raise FileNotFoundError(
            f"Provided dataset path {dataset_path} does not exist. Please provide a valid path through the function arguments"
        )


def tseries_coverage(
    variables,
    dataset_path=None,
    member=None,
    regex=r"(\d{6,8})-(\d{6,8})",
    delimiter=".",
    **_,
):
    """The first and last days the tseries files under dataset_path cover for
    every one of variables, read from their file names like the readers do;
    (None, None) when there are none to read."""
    if dataset_path is None or not Path(dataset_path).exists():
        return None, None
    files_by_var = parse_dataset(
        variables,
        dataset_path,
        "0001-01-01",
        "9999-12-31",
        regex=regex,
        space_character=delimiter,
    )
    spans = []
    for files in files_by_var.values():
        ranges = []
        for f in files:
            m = re.search(regex, os.path.basename(f))
            if m is None or (member is not None and member not in f):
                continue
            first, last = get_date_range_from_filename(f, regex)
            # A YYYYMM end names the file's last month, which it covers to
            # the month's last day (CESM-MOM stamps monthly means mid-month).
            if len(m.group(2)) == 6:
                last += pd.offsets.MonthEnd(0)
            ranges.append((first, last))
        if ranges:
            spans.append((min(r[0] for r in ranges), max(r[1] for r in ranges)))
    if not spans:
        return None, None
    return max(s[0] for s in spans), min(s[1] for s in spans)


def read_single_variable_tseries_data(
    when,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    output_folder,
    output_filename,
    variables,
    dataset_path,
    member,
    date_format,
    regex,
    delimiter,
    lat_name,
    lon_name,
    preview,
    data_freq=None,
    grid_coords=None,
):
    """
    Shared implementation for reading single-variable-per-file (tseries) output
    for a bounding box, used by both CESM_POP_OUTPUT.get_cesm_single_variable_data
    and CESM_MOM_OUTPUT.get_mom6_single_variable_data - the CESM tseries file
    convention (one variable per file series, date range in the filename) shows
    up for both CESM-POP and native MOM6 output.

    when (a TimeRequest) names the records to keep, and data_freq is the
    cadence of the files, checked against them (see check_data_freq).

    grid_coords optionally maps a variable name to its own (lat_name, lon_name)
    pair, overriding lat_name/lon_name for that variable - needed for MOM6's
    C-grid, where uo/vo live on different horizontal dims than the tracer grid.
    """
    validate_dataset_path(dataset_path)
    start_date, end_date = when.start, when.end
    # parse_dataset uses dateutil internally, so pass full ISO dates here -
    # date_format (e.g. "%Y%m" for monthly tseries) is ambiguous/unparseable
    # by dateutil and is only used for matching dates embedded in filenames.
    variable_info = parse_dataset(
        variables,
        dataset_path,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
        date_format=date_format,
        regex=regex,
        space_character=delimiter,
    )

    # Filter to the requested ensemble member (e.g. for CESM2-LENS2)
    if member is not None:
        for var in variable_info:
            variable_info[var] = [f for f in variable_info[var] if member in f]

    paths = subset_dataset(
        variable_info=variable_info,
        output_path=output_folder,
        lat_min=lat_min - 1.5,
        lat_max=lat_max + 1.5,
        lon_min=lon_min - 1.5,
        lon_max=lon_max + 1.5,
        lat_name=lat_name,
        lon_name=lon_name,
        dates=(
            start_date.strftime(date_format),
            end_date.strftime(date_format),
        ),
        preview=preview,
        when=when,
        data_freq=data_freq,
        grid_coords=grid_coords,
    )

    # Merge the file into the specified output file.
    if output_filename is not None:
        print(
            f"Merging the files since output file is specified, into {Path(output_folder)/output_filename}"
        )
        # parallel=True is unsafe here: the netCDF4 backend isn't thread-safe
        # for concurrent metadata reads across multiple files, and can
        # silently drop/corrupt variables (or crash) under dask's threaded
        # scheduler instead of raising a clear error.
        existing_files = [p for p in paths if Path(p).is_file()]
        if not existing_files:
            print(f"No subset files to merge into {output_filename}; skipping merge.")
        else:
            merged = xr.open_mfdataset(
                existing_files, combine="by_coords", decode_timedelta=False
            )
            merged.to_netcdf(Path(output_folder) / output_filename)

    return paths


def parse_dataset(
    variable_names: list[str],
    dataset_path: str | Path,
    start_date: str,
    end_date: str,
    date_format: str = "%Y%m%d",
    regex=r"(\d{6,8})-(\d{6,8})",
    space_character=".",
) -> dict:
    """
    Parses the dataset to find variable names and their corresponding file paths.

    Args:
        variable_names (list[str]): List of variable names to search for.
        dataset_path (str | xr.Dataset | Path): Path to the dataset (or folder with dataset)
        space_character (str): Character that separates words in variable names in the filenames. Default is ".".

    Returns:
        dict: A dictionary with variable names as keys and their file paths as values.
    """
    print("Parsing dataset...")
    start_date = parser.parse(start_date)
    end_date = parser.parse(end_date)
    # Create a dictionary to hold variable names and their file paths
    variable_info = {v: [] for v in variable_names}

    dataset_path = Path(dataset_path)
    if dataset_path.is_file():
        for v in variable_names:
            variable_info[v] = [str(dataset_path.resolve())]
        return variable_info
    if not dataset_path.is_dir():
        raise ValueError("dataset_path must be a string, Path to existing file(s)")

    def scan_for_vars(root, candidate_vars):
        # os.walk classifies entries as files/dirs from the directory read
        # itself, avoiding a separate stat() syscall per entry (unlike
        # Path.rglob(...) + Path.is_file()) - important on slow/networked
        # archive filesystems with tens of thousands of files.
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                file_path = Path(dirpath) / fname
                matched = [
                    v
                    for v in candidate_vars
                    if (space_character + v + space_character) in str(file_path)
                ]
                if not matched:
                    continue
                s = str(file_path.resolve())
                rng = get_date_range_from_filename(s, regex)
                if rng is None:  # no date range found in filename regex, skip this file
                    continue
                dt1, dt2 = rng
                # Interval-overlap test, not an endpoints-in-window test: a
                # file spanning the whole requested window (e.g. LENS2's
                # decadal chunks, FOSI's annual files) has both endpoints
                # outside [start_date, end_date] but still contains the data.
                if dt1 <= end_date and dt2 >= start_date:
                    for v in matched:
                        variable_info[v].append(s)

    # CESM tseries archives are commonly organized as one subdirectory per
    # variable (e.g. CESM2-LENS2) - search there directly instead of walking
    # the entire (potentially huge) archive tree.
    remaining_vars = []
    for v in variable_names:
        var_dir = dataset_path / v
        if var_dir.is_dir():
            scan_for_vars(var_dir, [v])
        else:
            remaining_vars.append(v)

    if remaining_vars:
        scan_for_vars(dataset_path, remaining_vars)

    # Print the found file paths
    for v in variable_info:
        print(f"{len(variable_info[v])} file(s) found for variable '{v}'")

    return variable_info


def convert_cftime_to_numeric(ds, time_var_name="time", calendar: Calendar = NOLEAP):
    """
    Converts a cftime time coordinate to numeric (days since 1850-01-01, noleap)
    for safe NetCDF serialization; a no-op if the coordinate isn't cftime.
    """
    if not isinstance(ds[time_var_name].values[0], cftime.datetime):
        return ds
    time_values = ds[time_var_name].values
    units = "days since 1850-01-01 00:00:00"
    # This file is an intermediate read back by xarray/cftime, not by MOM6,
    # so both roles here want the cf spelling.
    cal_name = calendar.cf
    numeric_time = cftime.date2num(time_values, units=units, calendar=cal_name)
    ds = ds.assign_coords(
        **{
            time_var_name: (
                time_var_name,
                numeric_time,
                {"units": units, "calendar": cal_name},
            )
        }
    )
    return drop_extra_cftime_vars(ds)


def _first_day(times):
    """Each cftime or datetime64 time at midnight of its day."""
    if isinstance(times[0], cftime.datetime):
        return np.array(
            [t.replace(hour=0, minute=0, second=0, microsecond=0) for t in times]
        )
    return times.astype("datetime64[D]").astype(times.dtype)


def date_means_at_interval_start(ds, time_var_name="time"):
    """CESM-POP stamps a mean at the end of its averaging interval (a January
    mean at Feb 1): date those records, and their time bounds, at the first
    day of the interval instead. The day, because POP's first interval starts
    a model step after midnight (00:31:40 in CESM-HR). Records stamped
    anywhere else, like MOM6's mid-interval means, are left as they are."""
    bounds = ds[time_var_name].attrs.get("bounds")
    if bounds not in ds.variables:
        return ds
    time = ds[time_var_name].values
    start, end = ds[bounds].values[:, 0], ds[bounds].values[:, 1]
    at_end = time == end
    if not at_end.any():
        return ds
    start = np.where(at_end, _first_day(start), start)
    ds = ds.assign_coords(
        {
            time_var_name: (
                time_var_name,
                np.where(at_end, start, time),
                ds[time_var_name].attrs,
            )
        }
    )
    ds[bounds] = (ds[bounds].dims, np.stack([start, end], axis=1))
    return ds


def check_data_freq(ds, data_freq, time_var_name="time", source=""):
    """Check that ds's records are data_freq apart: it only describes the
    files, so one that doesn't match them is the user's to fix."""
    time = ds[time_var_name].values
    if data_freq is not None and len(time) > 1:
        spacing = np.median(pd.to_timedelta(np.diff(time)) / pd.Timedelta(days=1))
        expected = frequency_step(data_freq) / pd.Timedelta(days=1)
        if not 0.8 <= spacing / expected <= 1.25:
            # The usual cadence these records match, to name in the message.
            match = next(
                (
                    freq
                    for freq in ("h", "3h", "6h", "D", "5D", "MS", "QS", "YS")
                    if 0.8
                    <= spacing / (frequency_step(freq) / pd.Timedelta(days=1))
                    <= 1.25
                ),
                None,
            )
            raise ValueError(
                f"{source} holds records about {spacing:.3g} days apart, which "
                f"isn't data_freq={data_freq!r} ({expected:.3g} days). Pass the "
                "cadence of that data as data_freq"
                + (f", e.g. data_freq={match!r}." if match else ".")
            )


def bbox_mask(
    ds, lat_min, lat_max, lon_min, lon_max, lat_name="lat", lon_name="lon", buffer_deg=0
):
    """
    Boolean lat/lon mask for subsetting a dataset, handling both 0-360 and
    -180-180 longitude conventions.

    ``lon_min``/``lon_max`` name a contiguous arc running eastward from
    ``lon_min``, the way ``Grid.get_bounding_boxes`` returns one. An arc that
    crosses the antimeridian ends past 180 -- 170 to 190, say -- because no
    pair of in-range ends can describe one. Normalising each end on its own
    turns that into 170 to -170 and selects nothing, so measure each source
    longitude as an offset eastward from the start of the arc instead: a point
    is inside when its offset is no wider than the arc. Taking that offset
    modulo 360 puts both the source's convention and the crossing to rest, so
    neither needs a branch of its own.
    """
    lat_min_buf, lat_max_buf = lat_min - buffer_deg, lat_max + buffer_deg
    lon_min_buf, lon_max_buf = lon_min - buffer_deg, lon_max + buffer_deg

    width = lon_max_buf - lon_min_buf
    if width >= 360:
        lon_inside = xr.ones_like(ds[lon_name], dtype=bool)
    else:
        lon_inside = (ds[lon_name] - lon_min_buf) % 360 <= width

    mask = (ds[lat_name] >= lat_min_buf) & (ds[lat_name] <= lat_max_buf) & lon_inside
    return mask.compute()


def subset_dataset(
    variable_info: dict,
    output_path: str | Path,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    lat_name="lat",
    lon_name="lon",
    dates=None,
    preview: bool = False,
    when=None,
    data_freq: str | None = None,
    grid_coords: dict | None = None,
) -> None:
    """
    Subsets (and merges) the dataset based on the provided variable names and
    geographical bounds into the output path.

    Args:
        variable_info (dict): A dictionary with variable names as keys and their file paths as values.
        output_path (str | Path): The path where the subsetted dataset will be saved.
        lat_min (float): Minimum latitude for subsetting.
        lat_max (float): Maximum latitude for subsetting.
        lon_min (float): Minimum longitude for subsetting.
        lon_max (float): Maximum longitude for subsetting.
        lat_name (str): Default latitude coordinate name, used for any variable
            not listed in grid_coords. Default is "lat".
        lon_name (str): Default longitude coordinate name, used for any variable
            not listed in grid_coords. Default is "lon".
        dates (tuple): Just used for the file naming
        preview (bool): If True, only previews the subsetting without saving. Default is False.
        when (TimeRequest | None): The records to keep, thinned when it
            has dates: the files hold whole years or decades. None keeps
            every record.
        data_freq (str | None): The files' cadence, checked against them
            (see check_data_freq). None skips the check.
        grid_coords (dict | None): Optional {var_name: (lat_name, lon_name)}
            override - needed for MOM6's C-grid, where uo/vo live on different
            horizontal dims than the tracer grid, so a single lat_name/lon_name
            pair can't mask every variable correctly.
    """

    # Create the output directory if it does not exist
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    grid_coords = grid_coords or {}
    # Each variable is loaded from its own file(s), so its mask is computed
    # fresh per variable (not cached/reused across the loop) - variables can
    # sit on different horizontal grid points with different lat/lon dims.
    output_file_paths = []
    for var_name, file_paths in variable_info.items():
        if dates is None:
            dates = ("NotSpecifiedDate", "NotSpecifiedDate")
        output_file = output_path / (
            f"{var_name}_subset_{lat_min}_{lat_max}_{lon_min}_{lon_max}_{dates[0]}_{dates[1]}"
            + (
                ""
                if when is None or when.dates is None
                else f"_sampled_{when.dates[0]:%Y%m%d}_{when.dates[-1]:%Y%m%d}_{len(when.dates)}"
            )
            + ".nc"
        )

        if output_file.exists():
            print(f"Subset already exists for {var_name}, skipping")
            output_file_paths.append(output_file)
            continue
        if not file_paths:
            print(f"No files found for variable: {var_name}")
            continue

        # Load the dataset for the variable
        ds = xr.open_mfdataset(file_paths, decode_timedelta=False)
        ds = date_means_at_interval_start(ds)
        check_data_freq(ds, data_freq, source=Path(file_paths[0]).parent)
        if when is not None:
            ds = when.select(ds)

        # Convert time. Saving to netcdf is not working with cftime objects.
        ds = convert_cftime_to_numeric(ds, time_var_name="time")

        var_lat_name, var_lon_name = grid_coords.get(var_name, (lat_name, lon_name))
        mask = bbox_mask(
            ds,
            lat_min,
            lat_max,
            lon_min,
            lon_max,
            var_lat_name,
            var_lon_name,
            buffer_deg=1,
        )

        # Subset the dataset based on the provided geographical bounds
        if not preview:
            subset_ds = ds.where(mask, drop=True)

            # Save the subsetted dataset to the output path

            subset_ds.load().to_netcdf(output_file)

            print(f"Subsetted dataset for variable '{var_name}' saved to {output_file}")
            output_file_paths.append(output_file)

    return output_file_paths


def get_date_range_from_filename(path, regex):
    fname = os.path.basename(path)
    m = re.search(regex, fname)
    if not m:
        return None

    def parse_date(datestr):
        if len(datestr) == 6:  # YYYYMM
            return datetime.strptime(datestr, "%Y%m")
        elif len(datestr) == 8:  # YYYYMMDD
            return datetime.strptime(datestr, "%Y%m%d")
        else:
            raise ValueError(f"Unexpected date format: {datestr}")

    start = parse_date(m.group(1))
    end = parse_date(m.group(2))
    return start, end


def drop_extra_cftime_vars(ds):
    drop_vars = []
    for name, var in ds.variables.items():
        if name != "time":
            # make sure the array isn’t empty
            if var.size > 0 and isinstance(first_value(var), cftime.datetime):
                drop_vars.append(name)
    return ds.drop_vars(drop_vars)


def first_value(da_var):
    arr = da_var.data  # could be numpy or dask

    if dask.is_dask_collection(arr):
        # only compute the first element, not the whole array
        return arr.ravel()[0].compute()
    else:
        return arr.ravel()[0]
