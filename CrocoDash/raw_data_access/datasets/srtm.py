import os
import requests
from pathlib import Path
from CrocoDash.raw_data_access.base import *


class SRTM(BaseProduct):
    product_name = "srtm"
    description = (
        "SRTM15+ is a global 15 arc-second resolution bathymetry/topography dataset "
        "compiled from SRTM land topography and satellite-derived ocean bathymetry."
    )
    link = "https://topex.ucsd.edu/WWW_html/srtm15_plus.html"

    @accessmethod(
        description="Python download of the SRTM15+ global bathymetry NetCDF file",
        type="python",
        how_to_use="No authentication required. Streams the full global file (~1.1 GB) directly. Requires the CrocoDash conda environment.",
    )
    def get_srtm_data_with_python(
        output_folder=None,
        output_filename=None,
    ):
        filename = output_filename or "SRTM15_V2.7.nc"
        if output_folder is None:
            output_folder = os.getcwd()
        os.makedirs(output_folder, exist_ok=True)
        local_path = os.path.join(output_folder, filename)
        file_url = "https://topex.ucsd.edu/pub/srtm15_plus/SRTM15_V2.7.nc"

        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return local_path

    @accessmethod(
        description="Bash script to download the SRTM15+ global bathymetry NetCDF file",
        type="script",
        how_to_use="No authentication required. Only requires `curl`. Downloads the full global SRTM15+ file (~1.1 GB).",
    )
    def get_srtm_data_script(
        output_folder=None,
        output_filename=None,
    ):
        filename = output_filename or "SRTM15_V2.7.nc"
        script = f"""#!/bin/bash
set -e

FILE_URL="https://topex.ucsd.edu/pub/srtm15_plus/SRTM15_V2.7.nc"
output_folder="{output_folder}"
FILENAME="{filename}"

mkdir -p "$output_folder"
curl -L "$FILE_URL" -o "$output_folder/$FILENAME"
"""
        output_folder = Path(output_folder)
        output_folder.mkdir(exist_ok=True)
        script_path = output_folder / "get_srtm_data.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)
        return script_path
