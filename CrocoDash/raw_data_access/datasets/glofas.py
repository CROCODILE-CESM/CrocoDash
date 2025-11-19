from pathlib import Path
from . import utils
import cdsapi
import pandas as pd
from CrocoDash.raw_data_access.base import *

class GLOFAS(BaseProduct):
    product_name = "glofas"
    description = "	GLOFAS (Global Flood Awareness System) is a public river discharge/runoff Product"
    @accessmethod
    @staticmethod
    def get_global_data_with_python(
        dates,
        output_folder=Path(""),
        output_filename="glofas_data.nc",
    ):
        """
        Downloads glofas data using cdsapi library. Note that users need to have an account with copernicus and have cdsapi installed and configured.

        Parameters
        ----------

        date : str, optional
            What dates to download.
        output_folder : str, optional
            Directory where downloaded files will be saved.

        """
        dataset = "cems-glofas-historical"
        start, end = pd.to_datetime(dates[0]), pd.to_datetime(dates[1])
        dates = pd.date_range(start=start, end=end)
        hyear = sorted(list({d.strftime("%Y") for d in dates}))
        hmonth = sorted(list({d.strftime("%m") for d in dates}))
        hday = sorted(list({d.strftime("%d") for d in dates}))

        request = {
            "system_version": ["version_4_0"],
            "hydrological_model": ["lisflood"],
            "product_type": ["consolidated"],
            "variable": ["river_discharge_in_the_last_24_hours"],
            "hyear": hyear,
            "hmonth": hmonth,
            "hday": hday,
            "data_format": "netcdf",
            "download_format": "zip",
        }

        client = cdsapi.Client()
        path = output_folder / output_filename
        client.retrieve(dataset, request, path)
        return path

    @accessmethod
    @staticmethod
    def get_processed_global_glofas_script_for_cli(
        dates="UNUSED",
        output_folder=Path(""),
        output_filename="processed_glofas.nc",
    ):
        """
        Downloads chlor_a data from the CESM inputdata repository by generating a script users can run in their terminal.
        Parameters
        ----------

        date : str, optional
            Currently unused; placeholder for future date-based filtering.
        lat_min : float, optional
            Currently unused; placeholder for future spatial filtering.
        lat_max : float, optional
            Currently unused; placeholder for future spatial filtering.
        lon_min : float, optional
            Currently unused; placeholder for future spatial filtering.
        lon_max : float, optional
            Currently unused; placeholder for future spatial filtering.
        output_folder : str, optional
            Directory where downloaded files will be saved.
        output_filename : str, optional
            filename in output directory

        """

        return utils.write_bash_curl_script(
            url="https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata/ocn/mom/croc/rof/glofas/processed_glofas_data.nc",
            script_name="get_processed_glofas.sh",
            output_folder=output_folder,
            output_filename=output_filename,
        )
