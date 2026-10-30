from pathlib import Path
from CrocoDash.raw_data_access.datasets import utils
import cdsapi
from CrocoDash.raw_data_access.base import *


class GLOFAS(DatedBaseProduct):
    product_name = "glofas"
    description = "	GLOFAS (Global Flood Awareness System) is a public river discharge/runoff Product"
    link = "https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=download"
    time_sampling = TimeSampling("D", "mean")

    @accessmethod(
        subsample=True,
        description="Gets glofas raw data through the cdsapi package",
        type="python",
        how_to_use="Requires a CDS API key — register at https://cds.climate.copernicus.eu and configure ~/.cdsapirc before use.",
    )
    def get_global_data_with_python(
        when: TimeRequest,
        output_folder=Path(""),
        output_filename="glofas_data.nc",
    ):
        """
        Downloads glofas data using cdsapi library. Note that users need to have an account with copernicus and have cdsapi installed and configured.

        Parameters
        ----------
        when : TimeRequest
            The days to request: every day from its start to its end, or its
            dates when thinned.
        output_folder : str, optional
            Directory where downloaded files will be saved.
        output_filename : str, optional
            Filename to write inside ``output_folder``.

        """
        dataset = "cems-glofas-historical"
        days = when.days()
        hyear = sorted({d.strftime("%Y") for d in days})
        hmonth = sorted({d.strftime("%m") for d in days})
        hday = sorted({d.strftime("%d") for d in days})

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
        path = Path(output_folder) / output_filename
        client.retrieve(dataset, request, path)
        return path

    @accessmethod(
        description="Generates bash script for access to CESM Inputdata processed glofas data",
        type="script",
        how_to_use="Only requires `curl`. Downloads pre-processed global GloFAS discharge data from CESM inputdata.",
    )
    def get_processed_global_glofas_script_for_cli(
        output_folder=Path(""),
        output_filename="processed_glofas.nc",
    ):
        """
        Downloads pre-processed global GloFAS discharge data from the CESM
        inputdata repository by generating a script users can run in their terminal.
        It takes no when: the published file is a fixed global dataset.

        Parameters
        ----------
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
