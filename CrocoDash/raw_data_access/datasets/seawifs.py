from pathlib import Path
from . import utils
from CrocoDash.raw_data_access.base import *


class SeaWIFS(BaseProduct):
    product_name = "seawifs"
    description = "SEAWIFS is a Chlorophyll Dataset for MOM6"
    link = "https://oceandata.sci.gsfc.nasa.gov/getfile/SEASTAR_SEAWIFS_GAC.19980201_20100228.L3m.MC.CHL.chlor_a.9km.nc"
    @accessmethod(description="Generates bash script for direct CLI access to chlorophyll data (No Package Required)", type="script")
    def get_global_seawifs_script_for_cli(
        output_folder=None,
        output_filename="UNUSED",
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
        output_folder : str, optional
            Directory where downloaded files will be saved.

        """

        script = f"""#!/bin/bash

                    # Set output directory
                    output_folder="{output_folder}"
                    mkdir -p "$output_folder"

                    # Perform file search, filter for desired files, and download using Earthdata credentials
                    wget -q --post-data="results_as_file=1&sensor_id=6&dtid=1123&sdate=1997-08-31%2000:00:00&edate=2025-05-13%2023:59:59&subType=1&addurl=1&prod_id=chlor_a&resolution_id=9km&period=MC" \\
                    -O - https://oceandata.sci.gsfc.nasa.gov/api/file_search | \\
                    grep 'L3m.MC.CHL.chlor_a.9km' | \\
                    (cd "$output_folder" && wget --user={username} --ask-password --auth-no-challenge=on -N --wait=0.5 --random-wait -i -)
                    """
        output_folder = Path(output_folder)
        output_folder.mkdir(exist_ok=True)
        script_path = output_folder / "get_seawifs_data.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)
        return script_path

    @accessmethod(description="	Generates bash script for direct CLI access to processed chlorophyll data (No Package Required)",type="script")
    def get_processed_global_seawifs_script_for_cli(
        output_folder=Path(""),
        output_filename="processed_seawifs.nc",
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
            url="https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata/ocn/mom/croc/chl/data/SeaWIFS.L3m.MC.CHL.chlor_a.0.25deg.nc",
            script_name="get_processed_seawifs.sh",
            output_folder=output_folder,
            output_filename=output_filename,
        )
