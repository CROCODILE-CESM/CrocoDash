"""
Data Access Module -> Glorys
"""

import xarray as xr
import glob
import os
import copernicusmarine
import regional_mom6 as rm6
from pathlib import Path
from CrocoDash.raw_data_access.utils import fill_template
import pandas as pd
from .utils import convert_lons_to_180_range
from CrocoDash.raw_data_access.base import *


class GLORYS(ForcingProduct):
    product_name = "glorys"
    description = "GLORYS (Global Ocean Physics Reanalysis) is a public dataset provided through the copernicus marine service., https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/description"
    time_var_name = "time"
    time_units = "days"
    boundary_fill_method = "regional_mom6"
    tracer_x_coord = "longitude"
    tracer_y_coord = "latitude"
    u_var_name = "uo"
    v_var_name = "vo"
    u_y_coord = "latitude"
    u_x_coord = "longitude"
    v_x_coord = "longitude"
    v_y_coord = "latitude"
    u_lat_coord = "latitude"
    u_lon_coord = "longitude"
    v_lat_coord = "latitude"
    v_lon_coord = "longitude"
    tracer_lat_coord = "latitude"
    tracer_lon_coord = "longitude"
    eta_var_name = "zos"
    depth_coord = "depth"
    tracer_var_names = {"temp": "thetao", "salt": "so"}

    @accessmethod(description="Gathers GLORYS data from RDA on computers with access to glade/rda", type="python")
    @staticmethod
    def get_glorys_data_from_rda(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        output_folder=Path(""),
        output_filename="raw_glorys.nc",
        variables=[
            "time",
            "latitude",
            "longitude",
            "depth",
            "zos",
            "uo",
            "vo",
            "so",
            "thetao",
        ],
    ) -> xr.Dataset:
        """
        Gather GLORYS Data on Derecho Computers from the campaign storage and return the dataset sliced to the llc and urc coordinates at the specific dates
        """
        dates = pd.date_range(start=dates[0], end=dates[1]).to_pydatetime().tolist()
        path = Path(output_folder) / output_filename
        GLORYS.logger.info(f"Downloading Glorys data from RDA to {path}")

        # Access RDA Path
        ds_in_path = "/glade/campaign/collections/rda/data/d010049/"
        ds_in_files = []
        date_strings = [date.strftime("%Y%m%d") for date in dates]

        # Adjust lat lon inputs to make sure they are in the correct range of -180 to 180
        lon_min, lon_max = convert_lons_to_180_range(lon_min, lon_max)

        for date in date_strings:
            pattern = os.path.join(ds_in_path, "**", f"*_{date}_*.nc")
            ds_in_files.extend(glob.glob(pattern, recursive=True))
        ds_in_files = sorted(ds_in_files)

        ds = xr.open_mfdataset(
            ds_in_files, decode_times=False, engine="h5netcdf", parallel=True
        )[variables]

        if lon_min * lon_max > 0:
            dataset = ds.sel(
                latitude=slice(lat_min - 1, lat_max + 1),
                longitude=slice(lon_min - 1, lon_max + 1),
            )
        else:
            dataset = xr.concat(
                [
                    ds.sel(
                        latitude=slice(lat_min - 1, lat_max + 1),
                        **{"longitude": slice(lon_min - 1, 360)},
                    ),
                    ds.sel(
                        latitude=slice(lat_min - 1, lat_max + 1),
                        **{"longitude": slice(-180, lon_max + 1)},
                    ),
                ],
                dim="longitude",
            )

            # convert longitude from degree west to degree east
            dataset["longitude"] = (360 - dataset["longitude"]) % 360
            dataset = dataset.sortby("longitude")

        dataset.to_netcdf(path)
        return path

    @accessmethod(description="Python request with copernicusmarine api", type="python")
    @staticmethod
    def get_glorys_data_from_cds_api(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        output_folder=None,
        output_filename=None,
        variables=["zos", "uo", "vo", "so", "thetao"],
    ):
        """
        Using the copernucismarine api, query GLORYS data (any dates)
        """
        start_datetime = dates[0]
        end_datetime = dates[-1]
        dataset_id = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
        response = copernicusmarine.subset(
            dataset_id=dataset_id,
            minimum_longitude=lon_min - 1,
            maximum_longitude=lon_max + 1,
            minimum_latitude=lat_min - 1,
            maximum_latitude=lat_max + 1,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            variables=variables,
            output_folderectory=output_folder,
            output_filenamename=output_filename,
        )
        return Path(output_folder) / output_filename

    @accessmethod(description="	Generates bash script for direct CLI run with the copernicusmarine package", type="script")
    @staticmethod
    def get_glorys_data_script_for_cli(
        dates: tuple,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        output_folder,
        output_filename,
        variables=None,
    ) -> None:
        """
        Script to run the GLORYS data query for the CLI
        """
        modify_existing = False
        if os.path.exists(output_folder / Path("get_glorys_data.sh")):
            modify_existing = True
        path = rm6.get_glorys_data(
            [lon_min, lon_max],
            [lat_min, lat_max],
            [dates[0], dates[-1]],
            os.path.splitext(output_filename)[0],
            output_folder,
            modify_existing=modify_existing,
        )
        GLORYS.logger.info(
            f"This data access method retuns a script at path {path} to run to get access data "
        )
        return path
