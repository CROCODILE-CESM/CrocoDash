"""
Data Access Module -> CESM ocean output

Two products, split because they have different variable/coordinate naming
conventions (and so need different ForcingProduct metadata):
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
import pandas as pd

from CrocoDash.raw_data_access.base import *


class CESM_POP_OUTPUT(ForcingProduct):
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
    calendar = "noleap"
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

    @accessmethod(
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
        dates: list,
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
    ):
        # CESM-POP tseries output needs the month-shift correction for its
        # average-endpoint timestamp labeling convention.
        return read_single_variable_tseries_data(
            dates,
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
            apply_month_shift=True,
        )


class CESM_MOM_OUTPUT(ForcingProduct):
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
    tracer_var_names = {"temp": "thetao", "salt": "so"}

    @accessmethod(
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
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename=None,
        variables=["zos", "thetao", "so", "uo", "vo"],
        dataset_path="/glade/u/home/manishrv/scratch/archive/gibraltar_parent/ocn/hist/z_files",
        file_glob="*.nc",
        time_var_name="time",
        buffer_deg=1.5,
        preview=False,
    ):
        validate_dataset_path(dataset_path)

        files = sorted(Path(dataset_path).glob(file_glob))
        if not files:
            raise FileNotFoundError(
                f"No files matching glob '{file_glob}' found in {dataset_path}."
            )

        ds = xr.open_mfdataset(files, combine="by_coords")

        # Unlike CESM_POP_OUTPUT.get_cesm_single_variable_data, no month-shift is
        # applied here - that shift is specific to the CESM-POP tseries
        # convention, not native MOM6 output.
        ds = convert_cftime_to_numeric(ds, time_var_name=time_var_name)

        # convert_cftime_to_numeric re-encodes a cftime coordinate as numeric
        # and stamps its units/calendar onto the coordinate attrs; match dates
        # to that same encoding so the slice bounds compare correctly.
        parsed_dates = pd.to_datetime(dates)
        time_attrs = ds[time_var_name].attrs
        if "units" in time_attrs and "calendar" in time_attrs:
            sel_dates = cftime.date2num(
                parsed_dates.to_pydatetime(),
                units=time_attrs["units"],
                calendar=time_attrs["calendar"],
            )
        else:
            sel_dates = parsed_dates
        ds = ds.sel({time_var_name: slice(sel_dates[0], sel_dates[-1])})
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
        dates: list,
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
    ):
        # Native MOM6 output doesn't need the CESM-POP month-shift correction.
        return read_single_variable_tseries_data(
            dates,
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
            apply_month_shift=False,
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
        raise FileNotFoundError(f"Provided dataset path {dataset_path} does not exist.")


def read_single_variable_tseries_data(
    dates,
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
    apply_month_shift,
    grid_coords=None,
):
    """
    Shared implementation for reading single-variable-per-file (tseries) output
    for a bounding box, used by both CESM_POP_OUTPUT.get_cesm_single_variable_data
    and CESM_MOM_OUTPUT.get_mom6_single_variable_data - the CESM tseries file
    convention (one variable per file series, date range in the filename) shows
    up for both CESM-POP and native MOM6 output.

    grid_coords optionally maps a variable name to its own (lat_name, lon_name)
    pair, overriding lat_name/lon_name for that variable - needed for MOM6's
    C-grid, where uo/vo live on different horizontal dims than the tracer grid.
    """
    validate_dataset_path(dataset_path)
    start_date, end_date = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
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
        apply_month_shift=apply_month_shift,
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
        merged = xr.open_mfdataset(paths, combine="by_coords", decode_timedelta=False)
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
                dt1, dt2 = get_date_range_from_filename(s, regex)
                if (dt1 >= start_date and dt1 <= end_date) or (
                    dt2 >= start_date and dt2 <= end_date
                ):
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


def convert_cftime_to_numeric(ds, time_var_name="time", apply_month_shift=False):
    """
    Converts a cftime time coordinate to numeric (days since 1850-01-01, noleap)
    for safe NetCDF serialization; a no-op if the coordinate isn't cftime.
    apply_month_shift is specific to the CESM-POP tseries convention (average-
    endpoint timestamp labeling) and should not be used for native MOM6 output.
    """
    if not isinstance(ds[time_var_name].values[0], cftime.datetime):
        return ds
    time_values = ds[time_var_name].values
    if apply_month_shift:
        time_values = [subtract_month(t) for t in time_values]
    units = "days since 1850-01-01 00:00:00"
    calendar = "noleap"
    numeric_time = cftime.date2num(time_values, units=units, calendar=calendar)
    ds = ds.assign_coords(
        **{
            time_var_name: (
                time_var_name,
                numeric_time,
                {"units": units, "calendar": calendar},
            )
        }
    )
    return drop_extra_cftime_vars(ds)


def bbox_mask(
    ds, lat_min, lat_max, lon_min, lon_max, lat_name="lat", lon_name="lon", buffer_deg=0
):
    """
    Boolean lat/lon mask for subsetting a dataset, handling both 0-360 and
    -180-180 longitude conventions.
    """
    lat_min_buf, lat_max_buf = lat_min - buffer_deg, lat_max + buffer_deg
    lon_min_buf, lon_max_buf = lon_min - buffer_deg, lon_max + buffer_deg
    if ds[lon_name].max() > 180:
        lon_min_buf, lon_max_buf = lon_min_buf % 360, lon_max_buf % 360
    else:
        lon_min_buf = ((lon_min_buf + 180) % 360) - 180
        lon_max_buf = ((lon_max_buf + 180) % 360) - 180
    mask = (
        (ds[lat_name] >= lat_min_buf)
        & (ds[lat_name] <= lat_max_buf)
        & (ds[lon_name] >= lon_min_buf)
        & (ds[lon_name] <= lon_max_buf)
    )
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
    apply_month_shift: bool = True,
    grid_coords: dict | None = None,
) -> None:
    """
    Subsets (and merges) the dataset based on the provided variable names and geographical bounds into the output path
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
        apply_month_shift (bool): Apply the CESM-POP tseries average-endpoint
            timestamp correction. Default True (matches CESM-POP); set False for
            native MOM6 tseries output.
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
            f"{var_name}_subset_{lat_min}_{lat_max}_{lon_min}_{lon_max}_{dates[0]}_{dates[1]}.nc"
        )
        output_file_paths.append(output_file)
        if output_file.exists():
            print(f"Subset already exists for {var_name}, skipping")
            continue
        if not file_paths:
            print(f"No files found for variable: {var_name}")
            continue

        # Load the dataset for the variable
        ds = xr.open_mfdataset(file_paths, decode_timedelta=False)

        # Convert time. Saving to netcdf is not working with cftime objects.
        ds = convert_cftime_to_numeric(
            ds, time_var_name="time", apply_month_shift=apply_month_shift
        )

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


def subtract_month(dt):
    # subtract one month, rolling back year if necessary
    year = dt.year
    month = dt.month - 1
    if month == 0:
        month = 12
        year -= 1
    # keep day, hour, minute, second as is
    day = min(dt.day, 28)  # avoid invalid dates (Feb)
    return cftime.DatetimeNoLeap(year, month, day, dt.hour, dt.minute, dt.second)
