"""
Data Access Module -> Glorys
"""

import xarray as xr
import glob
import os
import copernicusmarine
from CrocoDash.rm6 import regional_mom6 as rm6
from pathlib import Path
from CrocoDash.data_access.utils import fill_template
import pandas as pd
from .utils import setup_logger

logger = setup_logger(__name__)

def get_glorys_data_from_rda(
    dates: list,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    output_dir=Path(""),
    output_file="raw_glorys.nc",
) -> xr.Dataset:
    """
    Gather GLORYS Data on Derecho Computers from the campaign storage and return the dataset sliced to the llc and urc coordinates at the specific dates
    """
    path = Path(output_dir) / output_file
    logger.info(f"Downloading Glorys data from RDA to {path}")
    # Set Variables That Can Be Dropped
    drop_var_lst = ["mlotst", "bottomT", "sithick", "siconc", "usi", "vsi"]
    dates = pd.date_range(start=dates[0], end=dates[1]).to_pydatetime().tolist()
    # Access RDA Path
    ds_in_path = "/glade/campaign/collections/rda/data/d010049/"
    ds_in_files = []
    date_strings = [date.strftime("%Y%m%d") for date in dates]
    for date in date_strings:
        pattern = os.path.join(ds_in_path, "**", f"*_{date}_*.nc")
        ds_in_files.extend(glob.glob(pattern, recursive=True))
    ds_in_files = sorted(ds_in_files)
    
    # Adjust lat lon inputs to make sure they are in the correct range of -180 to 180
    lat_lon = [lat_min, lat_max, lon_min, lon_max]
    lat_min, lat_max, lon_min, lon_max = [(num-360) if num > 180 else num for num in lat_lon]

    dataset = (
        xr.open_mfdataset(ds_in_files, decode_times=False)
        .drop_vars(drop_var_lst)
        .sel(
            latitude=slice(lat_min - 1, lat_max + 1),
            longitude=slice(lon_min - 1, lon_max + 1),
        )
    )

    dataset.to_netcdf(path)
    return path

def get_glorys_rda_piecewise(
    dates: list,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    step_days = None,
    output_dir=Path(""),
    output_file="raw_glorys.nc"):
    """
    Get GLORYS data in chunks when the time frame is too large.
    For example, if you set step_days = 5 it will
    get the data from the given date range 5 days at a time. 
    
    This will result in (total # days)/(step_days) number of files (e.g. for 30 days of data with step_size = 5, this would generate 6 files). These six files can then be regridded individually and merged together to avoid memory overuse. 
    
    Arguments:
        - dates (list): two element list of the form [start_date,end_date], date format must be acceptable by pd.date_range
        - lat_min (float): latitude minimum for your rectangular boundary
        - lat_max (float): latitude maximum for boundary
        - lon_min (float): longitude minimum for boundary
        - lon_max (float): longitude maximum for boundary
        - step_days (int): number of days each piecewise file should cover at a maximum (some may be shorter if time frame is not divisible by step_days). Default is None, indicating all of the data should be retrieved in one file.
        - output_dir (string): path where resulting data file(s) should be stored
        - output_file (string): name (or structure of name) for output files (e.g. output_file="raw_glorys.nc" -> raw_glorys[start_date]_[start_date+step_size].nc etc.)
        
        THIS DOC STRING NEEDS A LOT OF WORK, COULD BE WAY LESS RAMBLY, BUT I WANTED TO HAVE SOMETHING
    """
    
    if step_days == None:
        logger.info(f"Bypassing piecwise retrieval of glorys data. Retrieving entire time frame at once.")
        path = get_glorys_data_from_rda(
            dates = dates, 
            lat_min = lat_min,
            lat_max = lat_max,
            lon_min = lon_min,
            lon_max = lon_max,
            output_dir = output_dir,
            output_file = output_file,
            )
        return path
    
    if step_days <= 0:
        raise ValueError("step_days must be a positive integer or a None type")
    
    dates = pd.date_range(start=dates[0], end=dates[1]).to_pydatetime().tolist()
    print("TODO - Look into pd.date_range freq argument, does it catch remainder??")
    date_strings = [date.strftime("%Y%m%d") for date in dates]
    
    num_files = (len(dates)+step_days-1)//step_days # ceiling division of number of days with step_days
    
    path = Path(output_dir) / output_file
    
    logger.info(f"Downloading Glorys Data from RDA from {dates[0]} to {dates[-1]}.")
    logger.info(f"This will result in {num_files} total files.")
    
    ## Grab data step_days number of days at a time
    # Grab step_days sized windows from the dates
    date_ranges = [[date_strings[i], date_strings[i+4]] for i in range(0,len(date_strings)-step_days,step_days)]
    # Get any remainder
    remaining_days = len(dates)%step_days
    if (remaining_days != 0):
        date_ranges.append([date_strings[-remaining_days],date_strings[-1]])
        
    # DEV: Check that it returns the expected number of date ranges
    assert(len(date_ranges)==num_files),"DEV_ERROR: Error with date_ranges in get_glorys_rda_piecewise"
    
    # Now actually getting the data!
    format_output = output_file.rsplit('.',1)
    assert(len(format_output) == 2), "Please pass in an outputfile name with a valid file type ending (e.g. file.nc)"
    
    for date_range in date_ranges:
        adjusted_output = f"{format_output[0]}.{date_range[0]}_{date_range[1]}.{format_output[1]}"
        path = get_glorys_data_from_rda(
            dates = date_range, 
            lat_min = lat_min,
            lat_max = lat_max,
            lon_min = lon_min,
            lon_max = lon_max,
            output_dir = output_dir,
            output_file = adjusted_output,
            )
        
    logger.info(f"Successfull retrieved (probably, if there were no angry red errors) Glorys Data from RDA located in {output_dir} directory.")


def get_glorys_data_from_cds_api(
    dates,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    output_dir=None,
    output_file=None,
):
    """
    Using the copernucismarine api, query GLORYS data (any dates)
    """
    start_datetime = dates[0]
    end_datetime = dates[-1]
    variables = ["so", "uo", "vo", "zos", "thetao"]
    dataset_id = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
    response = copernicusmarine.subset(
        dataset_id=dataset_id,
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        variables=variables,
        output_directory=output_dir,
        output_filename=output_file,
    )
    return response


def get_glorys_data_script_for_cli(
    dates: tuple,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    output_dir,
    output_file,
) -> None:
    """
    Script to run the GLORYS data query for the CLI
    """
    modify_existing = False
    if os.path.exists(output_dir / Path("get_glorys_data.sh")):
        modify_existing = True
    path = rm6.get_glorys_data(
        [lon_min, lon_max],
        [lat_min, lat_max],
        [dates[0], dates[-1]],
        os.path.splitext(output_file)[0],
        output_dir,
        modify_existing=modify_existing,
    )
    logger.info(
        f"This data access method retuns a script at path {path} to run to get access data "
    )
    return path
