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


def get_glorys_data_from_rda(
    dates: list, lat_min, lat_max, lon_min, lon_max
) -> xr.Dataset:
    """
    Gather GLORYS Data on Derecho Computers from the campaign storage and return the dataset sliced to the llc and urc coordinates at the specific dates
    """

    # Set Variables That Can Be Dropped 
    drop_var_lst = ["mlotst", "bottomT", "sithick", "siconc", "usi", "vsi"]

    # Access RDA Path
    ds_in_path = "/glade/campaign/collections/rda/data/d010049/"
    ds_in_files = []
    date_strings = [date.strftime("%Y%m%d") for date in dates]
    for date in date_strings:
        pattern = os.path.join(ds_in_path, "**", f"*_{date}_*.nc")
        ds_in_files.extend(glob.glob(pattern, recursive=True))
    ds_in_files = sorted(ds_in_files)
    dataset = (
        xr.open_mfdataset(ds_in_files, decode_times=False)
        .drop_vars(drop_var_lst)
        .sel(latitude=slice(lat_min, lat_max), longitude=slice(lon_min, lon_max))
    )

    return dataset


def get_glorys_data_from_cds_api(
    dates,
    lon_min,
    lon_max,
    lat_min,
    lat_max,
    output_dir = None ,
    output_file = None,
) -> xr.Dataset:
    """
    Using the copernucismarine api, query GLORYS data (any dates)
    """
    start_datetime = dates[0]
    end_datetime = dates[-1]
    variables = ["so", "uo", "vo","zos", "thetao"]
    dataset_id = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
    ds = copernicusmarine.subset(
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
    return ds


def get_glorys_data_script_for_cli(
    dates: tuple, lat_min, lat_max, lon_min, lon_max, filename = "glorys.nc", download_path = ""
) -> None:
    """
    Script to run the GLORYS data query for the CLI
    """
    return rm6.get_glorys_data(
        [lon_min, lon_max],
        [lat_min, lat_max],
        [dates[0], dates[-1]],
        filename,
        download_path,
    )
