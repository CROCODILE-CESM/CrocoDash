import os
import requests
from zipfile import ZipFile
from pathlib import Path
from CrocoDash.raw_data_access.base import *

class GEBCO(BaseProduct):
    product_name = "gebco"
    description = "GEBCO (General Bathymetric Chart of the Ocean) is a public dataset of global ocean bathymetry"
    @accessmethod(description="Python request for global bathymetry data", type="python")
    def get_gebco_data_with_python(
        output_folder=None,
        output_filename=None,
    ):

        filename = output_filename or "GEBCO_2024.zip"
        if output_folder is None:
            output_folder = os.getcwd()  # current directory
        os.makedirs(output_folder, exist_ok=True)
        local_zip_path = os.path.join(output_folder, filename)
        file_url = "https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024/zip/"

        # Stream download
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            with open(local_zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        # Unzip the file
        with ZipFile(local_zip_path, "r") as zip_ref:
            zip_ref.extractall(output_folder)
        return

    @accessmethod(description="get script to download global bathymetry data", type="script")
    def get_gebco_data_script(
        output_folder=None,
        output_filename=None,
    ):
        filename = output_filename or "GEBCO_2024.zip"
        script = f"""#!/bin/bash
    set -e

    # Variables
    FILE_URL="https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024/zip/"
    output_folder="{output_folder}"
    FILENAME="{filename}"
    ZIP_PATH="$output_folder/$FILENAME"

    # Make sure the output directory exists
    mkdir -p "$output_folder"

    # Download the file
    curl -L "$FILE_URL" -o "$ZIP_PATH"

    # Unzip the file
    unzip -o "$ZIP_PATH" -d "$output_folder"
    """
        output_folder = Path(output_folder)
        output_folder.mkdir(exist_ok=True)
        script_path = output_folder / "get_gebco_data.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)
        return script_path
