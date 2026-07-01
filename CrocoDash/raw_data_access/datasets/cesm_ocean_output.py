"""
Data Access Module -> CESM ocean output (CESM-HR FOSI and CESM2-LENS2)
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


class CESM_OCEAN_OUTPUT(ForcingProduct):
    product_name = "cesm_ocean_output"
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
        if not Path(dataset_path).exists():
            raise FileNotFoundError(
                f"Provided dataset path {dataset_path} does not exist."
            )
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
        )

        # Merge the file into the specified output file.
        if output_filename is not None:
            print(
                f"Merging the files since output file is specified, into {Path(output_folder)/output_filename}"
            )
            merged = xr.open_mfdataset(
                paths, combine="by_coords", parallel=True, decode_timedelta=False
            )
            merged.to_netcdf(Path(output_folder) / output_filename)

        return paths

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
        output_folder=Path(""),
        output_filename=None,
        variables=["zos", "thetao", "so", "uo", "vo"],
        dataset_path=None,
        file_glob="*.nc",
        lat_name="yh",
        lon_name="xh",
        time_var_name="time",
        buffer_deg=1.5,
        preview=False,
    ):
        if dataset_path is None or not Path(dataset_path).exists():
            raise FileNotFoundError(
                f"Provided dataset path {dataset_path} does not exist."
            )

        files = sorted(Path(dataset_path).glob(file_glob))
        if not files:
            raise FileNotFoundError(
                f"No files matching glob '{file_glob}' found in {dataset_path}."
            )

        ds = xr.open_mfdataset(files, combine="by_coords", decode_timedelta=False)

        # Unlike get_cesm_single_variable_data, no month-shift is applied here -
        # that shift is specific to the CESM-POP tseries convention, not native
        # MOM6 output.
        ds = convert_cftime_to_numeric(ds, time_var_name=time_var_name)

        ds = ds.sel({time_var_name: slice(dates[0], dates[-1])})

        mask = bbox_mask(
            ds, lat_min, lat_max, lon_min, lon_max, lat_name, lon_name, buffer_deg
        )
        ds = ds.where(mask, drop=True)

        keep_vars = [v for v in variables if v in ds.data_vars]
        missing_vars = [v for v in variables if v not in ds.data_vars]
        if missing_vars:
            CESM_OCEAN_OUTPUT.logger.warning(
                f"Requested variables not found in {dataset_path} (glob '{file_glob}'): "
                f"{missing_vars}"
            )
        ds = ds[keep_vars]

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
        lat_name (str): Name of the latitude variable in the dataset. Default is "lat".
        lon_name (str): Name of the longitude variable in the dataset. Default is "lon".
        dates (tuple): Just used for the file naming
        preview (bool): If True, only previews the subsetting without saving. Default is False.
    """

    # Create the output directory if it does not exist
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    mask = None
    # Iterate through each variable and its corresponding file paths
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
        # The CESM-POP tseries convention needs a month-shift to correctly
        # label average-endpoint timestamps.
        ds = convert_cftime_to_numeric(ds, time_var_name="time", apply_month_shift=True)

        if mask is None:
            mask = bbox_mask(
                ds, lat_min, lat_max, lon_min, lon_max, lat_name, lon_name, buffer_deg=1
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
