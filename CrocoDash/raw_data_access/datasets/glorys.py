"""
Data Access Module -> Glorys
"""

import xarray as xr
import glob
import os
import copernicusmarine
from pathlib import Path
import pandas as pd
from CrocoDash.raw_data_access.base import *

# Copernicus reads an end datetime as a cutoff, so a request ends on the last
# second of when's last day, or that day is dropped.
_TO_LAST_SECOND = pd.Timedelta(days=1, seconds=-1)


class GLORYS(MOM6ForcingProduct):
    product_name = "glorys"
    description = "GLORYS (Global Ocean Physics Reanalysis) is a public dataset provided through the copernicus marine service."
    link = "https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/description"
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
    calendar = GREGORIAN
    # Daily means, stamped at noon.
    time_sampling = TimeSampling("D", "mean")

    @classmethod
    def coverage(cls, method_name, **kwargs):
        # GLORYS starts on 1993-01-01, on RDA and Copernicus alike. Its end
        # moves as new days are added, so it is left open.
        return pd.Timestamp("1993-01-01"), None

    @accessmethod(
        subsample=True,
        description="Gathers GLORYS data from RDA on computers with access to glade/rda",
        type="python",
        how_to_use="Requires read access to /glade/campaign/collections/rda/data/d010049/ and the CrocoDash conda environment.",
        buf=1.0,
    )
    def get_glorys_data_from_rda(
        region: Region,
        when: TimeRequest,
        name=None,
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
    ) -> Path:
        """
        Gather GLORYS Data on Derecho Computers from the campaign storage: the
        files for when's days (its dates, when thinned), cut to region
        """
        path = Path(output_folder) / output_filename
        GLORYS.logger.info(f"Downloading Glorys data from RDA to {path}")

        # Access RDA Path
        ds_in_path = "/glade/campaign/collections/rda/data/d010049/"
        ds_in_files = []
        date_strings = [day.strftime("%Y%m%d") for day in when.days()]

        for date in date_strings:
            # Files are filed under a year subdirectory matching their own date
            # (e.g. d010049/1993/..._19930909_...nc). Scoping the glob to that
            # subdirectory avoids a recursive walk of the entire multi-decade
            # archive for every single day requested.
            pattern = os.path.join(ds_in_path, date[:4], f"*_{date}_*.nc")
            matches = glob.glob(pattern)
            if not matches:
                raise FileNotFoundError(f"No GLORYS file found for {date} at {pattern}")
            ds_in_files.extend(matches)
        ds_in_files = sorted(ds_in_files)

        ds = xr.open_mfdataset(
            ds_in_files,
            decode_times=False,
            engine="h5netcdf",
            parallel=True,
        )[variables]

        region.select(ds, lon="longitude", lat="latitude").to_netcdf(path)
        GLORYS.logger.info(f"Download of {path} complete.")
        return path

    @accessmethod(
        description="Python request with copernicusmarine api",
        type="python",
        how_to_use="Requires the CrocoDash conda environment and a Copernicus Marine account. Log in once with `copernicusmarine login` before use.",
        buf=1.0,
    )
    def get_glorys_data_from_cds_api(
        region: Region,
        when: TimeRequest,
        name=None,
        output_folder=None,
        output_filename=None,
        variables=["zos", "uo", "vo", "so", "thetao"],
    ):
        """
        Using the copernucismarine api, query GLORYS data (any dates). It
        takes longitudes past 180 and wraps them itself, so a box across 180E
        goes as one request.
        """
        dataset_id = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
        response = copernicusmarine.subset(
            dataset_id=dataset_id,
            minimum_longitude=region.lon_min,
            maximum_longitude=region.lon_max,
            minimum_latitude=region.lat_min,
            maximum_latitude=region.lat_max,
            start_datetime=f"{when.start:%Y-%m-%d %H:%M:%S}",
            end_datetime=f"{when.end + _TO_LAST_SECOND:%Y-%m-%d %H:%M:%S}",
            variables=variables,
            output_directory=output_folder,
            output_filename=output_filename,
        )
        return Path(output_folder) / output_filename

    @accessmethod(
        description="Generates bash script for direct CLI run with the copernicusmarine package",
        type="script",
        how_to_use="The generated get_glorys_data.sh requires the CrocoDash conda environment to run (`conda activate CrocoDash`). A Copernicus Marine account is needed — log in once with `copernicusmarine login` before running the script.",
        # Just under three GLORYS cells (3 x 1/12), as regional_mom6's script
        # used.
        buf=0.24,
    )
    def get_glorys_data_script_for_cli(
        region: Region,
        when: TimeRequest,
        output_folder,
        output_filename,
        variables=["zos", "uo", "vo", "so", "thetao"],
        name=None,
        **kwargs,
    ) -> Path:
        """
        Add this request's copernicusmarine subset line to get_glorys_data.sh
        in output_folder, so one script fetches every chunk of every
        boundary. A request already in it is not added again. variables=None
        fetches every variable, as it does for the CDS method.
        """
        line = (
            "copernicusmarine subset --dataset-id cmems_mod_glo_phy_my_0.083deg_P1D-m"
            + "".join(f" --variable {variable}" for variable in variables or [])
            + f" --start-datetime {when.start:%Y-%m-%dT%H:%M:%S}"
            f" --end-datetime {when.end + _TO_LAST_SECOND:%Y-%m-%dT%H:%M:%S}"
            f" --minimum-longitude {region.lon_min:.4f}"
            f" --maximum-longitude {region.lon_max:.4f}"
            f" --minimum-latitude {region.lat_min:.4f}"
            f" --maximum-latitude {region.lat_max:.4f}"
            " --minimum-depth 0 --maximum-depth 6000"
            f" -o {output_folder} -f {output_filename}"
        )
        path = Path(output_folder) / "get_glorys_data.sh"
        if not path.exists():
            path.write_text("#!/bin/bash\n")
        if line not in path.read_text().splitlines():
            with open(path, "a") as f:
                f.write(line + "\n")
        GLORYS.logger.info(
            f"This data access method returns a script at path {path} to run to get access data "
        )
        return path
