"""
Data Access Module -> CESM output
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


def get_cesm_data(
    dates: list,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    output_dir=Path(""),
    output_file=None,
    variables=["SSH", "TEMP", "SALT", "VVEL", "UVEL"],
    dataset_path="/glade/campaign/collections/cmip/CMIP6/CESM-HR/FOSI_BGC/HR/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001/ocn/proc/tseries/month_1",
    date_format: str = "%Y%m%d",
    regex=r"(\d{6,8})-(\d{6,8})",
    delimiter=".",
    preview=False,
):
    tracer_y_coord = "TLAT"
    tracer_x_coord = "TLONG"
    dates = pd.date_range(start=dates[0], end=dates[1]).to_pydatetime().tolist()
    variable_info = parse_dataset(
        variables,
        dataset_path,
        dates[0].strftime(date_format),
        dates[1].strftime(date_format),
        date_format=date_format,
        regex=regex,
        space_character=delimiter,
    )
    paths = subset_dataset(
        variable_info=variable_info,
        output_path=output_dir,
        lat_min=lat_min - 1.5,
        lat_max=lat_max + 1.5,
        lon_min=lon_min - 1.5,
        lon_max=lon_max + 1.5,
        lat_name=tracer_y_coord,
        lon_name=tracer_x_coord,
        dates=(dates[0].strftime(date_format),dates[1].strftime(date_format)),
        preview=preview,
    )

    # Merge the file into the specified output file.
    if output_file is not None:
        print(f"Merging the files since output file is specified, into {Path(output_dir)/output_file}")
        merged = xr.open_mfdataset(paths, combine='by_coords', parallel=True)
        merged.to_netcdf(Path(output_dir)/output_file)

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
    variable_info = {}
    for v in variable_names:
        variable_info[v] = []

    dataset_path = Path(dataset_path)
    if dataset_path.is_dir():
        for file_path in dataset_path.rglob("*"):
            if file_path.is_file():
                # Check each variable
                for v in variable_names:
                    if (space_character + v + space_character) in str(
                        file_path
                    ):  # check full path, not just name
                        s = str(file_path.resolve())
                        dt1, dt2 = get_date_range_from_filename(s, regex)
                        if (dt1 >= start_date and dt1 <= end_date) or (
                            dt2 >= start_date and dt2 <= end_date
                        ):
                            variable_info[v].append(s)

    elif dataset_path.is_file():
        for v in variable_names:
            variable_info[v] = [str(dataset_path.resolve())]
    else:
        raise ValueError("dataset_path must be a string, Path to existing file(s)")

    # Print the found file paths
    for v in variable_info:
        print(f"{len(variable_info[v])} file(s) found for variable '{v}'")

    return variable_info


def subset_dataset(
    variable_info: dict,
    output_path: str | Path,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    lat_name="lat",
    lon_name="lon",
    dates = None,
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
            dates = ("NotSpecifiedDate","NotSpecifiedDate")
        output_file = output_path / (f"{var_name}_subset_{lat_min}_{lat_max}_{lon_min}_{lon_max}_{dates[0]}_{dates[1]}.nc")
        output_file_paths.append(output_file)
        if output_file.exists():
            print(f"Subset already exists for {var_name}, skipping")
            continue
        if not file_paths:
            print(f"No files found for variable: {var_name}")
            continue

        # Load the dataset for the variable
        ds = xr.open_mfdataset(file_paths)
        dataset_is_degrees_east_longitude = False
        if ds[lon_name].max() > 180:
            dataset_is_degrees_east_longitude = True

        if dataset_is_degrees_east_longitude:
            lon_min = lon_min % 360
            lon_max = lon_max % 360
        else:
            lon_min = ((lon_min + 180) % 360) - 180
            lon_max = ((lon_max + 180) % 360) - 180

        # Convert time. Saving to netcdf is not working with cftime objects
        if isinstance(ds.time.values[0], cftime.datetime):
            adjusted_time = [subtract_month(t) for t in ds.time.values]
            units = "days since 1850-01-01 00:00:00"
            calendar = "noleap"
            numeric_time = cftime.date2num(
                adjusted_time, units=units, calendar=calendar
            )
            ds = ds.assign_coords(
                time=("time", numeric_time, {"units": units, "calendar": calendar})
            )

        # Drop the time_bound variable for the cesm if it exists, cftime isn't playing well, eventually this should be converted in the same way.
        ds = drop_extra_cftime_vars(ds)

        if mask is None:
            mask = (
                (ds[lat_name] >= lat_min - 1)
                & (ds[lat_name] <= lat_max + 1)
                & (ds[lon_name] >= lon_min - 1)
                & (ds[lon_name] <= lon_max + 1)
            )
            mask = mask.compute()

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