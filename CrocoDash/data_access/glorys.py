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


def get_glorys_data_with_pbs(
    output_template_path,
    start_date,
    end_date,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    output_dir,
    boundary_name,
    job_name="glorys",
    walltime="12:00:00",
    ncpus=1,
    mem=10,
    queue="main",
    project="ncgd0011",
    env_name = "CrocoDash"
):
    # Arguments to substitute into the template
    params = {
        "job_name": job_name,
        "walltime": walltime,
        "ncpus": ncpus,
        "mem": mem,
        "queue": queue,
        "boundary_name": boundary_name,
        "start_date": start_date,
        "end_date": end_date,
        "lon_min": lon_min,
        "lon_max": lon_max,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "output_dir": output_dir,
        "project": project,
        "env_name": env_name,
        "script_path": Path(__file__).resolve().parent / Path("glorys_data_api_request.py"),
    }
    template_path = Path(__file__).resolve().parent / Path("templates/template_glory_pbs.sh")
    fill_template(template_path, output_template_path, **params)


def get_glorys_data_from_rda(
    dates: list, lat_min, lat_max, lon_min, lon_max
) -> xr.Dataset:
    """
    Gather GLORYS Data on Derecho Computers from the campaign storage and return the dataset sliced to the llc and urc coordinates at the specific dates
    2005 Only
    """

    # Set
    drop_var_lst = ["mlotst", "bottomT", "sithick", "siconc", "usi", "vsi"]
    ds_in_path = "/glade/campaign/cgd/oce/projects/CROCODILE/glorys012/GLOBAL/"
    ds_in_files = []
    date_strings = [date.strftime("%Y%m%d") for date in dates]
    for date in date_strings:
        pattern = os.path.join(ds_in_path, "**", f"*{date}*.nc")
        ds_in_files.extend(glob.glob(pattern, recursive=True))
    ds_in_files = sorted(ds_in_files)
    dataset = (
        xr.open_mfdataset(ds_in_files, decode_times=False)
        .drop_vars(drop_var_lst)
        .sel(latitude=slice(lat_min, lat_max), longitude=slice(lon_min, lon_max))
    )

    return dataset


def get_glorys_data_from_cds_api(
    dataset_id: str,
    variables: list,
    start_datetime: tuple,
    end_datetime,
    lon_min,
    lon_max,
    lat_min,
    lat_max,
    output_dir,
    output_file,
) -> xr.Dataset:
    """
    Using the copernucismarine api, query GLORYS data (any dates)
    """
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
    dates: tuple, lat_min, lat_max, lon_min, lon_max, filename, download_path
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
