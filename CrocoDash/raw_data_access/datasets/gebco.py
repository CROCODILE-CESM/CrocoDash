import os
import requests
from zipfile import ZipFile
from pathlib import Path


def get_gebco_data_with_python(
    dates="UNUSED",
    lat_min="UNUSED",
    lat_max="UNUSED",
    lon_min="UNUSED",
    lon_max="UNUSED",
    output_dir=None,
    output_file=None,
):

    filename = output_file or "gebco_2024.zip"
    if output_dir is None:
        output_dir = os.getcwd()  # current directory
    os.makedirs(output_dir, exist_ok=True)
    local_zip_path = os.path.join(output_dir, filename)
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
        zip_ref.extractall(output_dir)
    return


def get_gebco_data_script(
    dates="UNUSED",
    lat_min="UNUSED",
    lat_max="UNUSED",
    lon_min="UNUSED",
    lon_max="UNUSED",
    output_dir=None,
    output_file="UNUSED",
):
    script = f"""#!/bin/bash
set -e

# Variables
FILE_URL="https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024/zip/"
OUTPUT_DIR="{output_dir}"
FILENAME="gebco_2024.zip"
ZIP_PATH="$OUTPUT_DIR/$FILENAME"

# Make sure the output directory exists
mkdir -p "$OUTPUT_DIR"

# Download the file
curl -L "$FILE_URL" -o "$ZIP_PATH"

# Unzip the file
unzip -o "$ZIP_PATH" -d "$OUTPUT_DIR"
"""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    script_path = output_dir / "get_gebco_data.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)
    return script_path
