from pathlib import Path
from . import utils


def get_global_glofas_script_for_cli(
    dates="UNUSED",
    lat_min="UNUSED",
    lat_max="UNUSED",
    lon_min="UNUSED",
    lon_max="UNUSED",
    output_dir=None,
    output_file="UNUSED",
    username="",
):
    """
    Downloads chlor_a data using NASA OceanData API with authentication.

    Parameters
    ----------
    username : str
        NASA Earthdata username (password will be prompted at runtime).
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
    output_dir : str, optional
        Directory where downloaded files will be saved.

    """

    raise NotImplementedError("Needs to be done! Go to here: https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=download")


def get_processed_global_glofas_script_for_cli(
    dates="UNUSED",
    lat_min="UNUSED",
    lat_max="UNUSED",
    lon_min="UNUSED",
    lon_max="UNUSED",
    output_dir=Path(""),
    output_file="processed_glofas.nc",
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
    output_dir : str, optional
        Directory where downloaded files will be saved.
    output_file : str, optional
        filename in output directory

    """

    return utils.write_bash_curl_script(
        url="https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata/ocn/mom/croc/rof/glofas/processed_glofas_data.nc",
        script_name="get_processed_glofas.sh",
        output_dir=output_dir,
        output_filename=output_file,
    )
