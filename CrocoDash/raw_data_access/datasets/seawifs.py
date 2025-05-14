import subprocess
from pathlib import Path
def get_global_seawifs_script_for_cli(dates="UNUSED",
    lat_min="UNUSED",
    lat_max="UNUSED",
    lon_min="UNUSED",
    lon_max="UNUSED",
    output_dir=None,
    output_file="UNUSED",username=""):
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

    script = f"""#!/bin/bash

                # Set output directory
                output_dir="{output_dir}"
                mkdir -p "$output_dir"

                # Perform file search, filter for desired files, and download using Earthdata credentials
                wget -q --post-data="results_as_file=1&sensor_id=6&dtid=1123&sdate=1997-09-04%2000:00:00&edate=2025-05-13%2023:59:59&subType=1&addurl=1&prod_id=chlor_a&resolution_id=9km&period=MC" \\
                -O - https://oceandata.sci.gsfc.nasa.gov/api/file_search | \\
                grep 'L3m.MC.CHL.chlor_a.9km' | \\
                (cd "$output_dir" && wget --user={username} --ask-password --auth-no-challenge=on -N --wait=0.5 --random-wait -i -)
                """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    script_path = output_dir / "get_seawifs_data.sh"
    script_path.write_text(script)
    script_path.chmod(0o755) 
    return script_path