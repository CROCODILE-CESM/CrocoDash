import os
import pandas as pd


def make_dates_end_inclusive(dates):
    """Return (start, end) as "%Y-%m-%d %H:%M:%S" strings, with the end pushed
    to the last second of its day.

    APIs that treat ``end_datetime`` as a literal cutoff (rather than a whole
    day) will otherwise silently drop everything after midnight on the last
    requested day.
    """
    start = pd.Timestamp(dates[0])
    end = pd.Timestamp(dates[-1]).normalize() + pd.Timedelta(
        hours=23, minutes=59, seconds=59
    )
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def convert_lons_to_180_range(*lons):
    lons_adj = []
    for lon in lons:
        lons_adj.append((lon + 180) % 360 - 180)
    return lons_adj


def write_bash_curl_script(url, script_name, output_folder, output_filename):
    full_script_path = os.path.join(output_folder, script_name)
    full_path = os.path.join(output_folder, output_filename)
    script_lines = [
        "#!/bin/bash",
        "",
        f"mkdir -p {output_folder}",
        f"curl -L '{url}' -o '{full_path}'",
        'echo "Download complete."',
    ]

    with open(full_script_path, "w") as f:
        f.write("\n".join(script_lines))
    os.chmod(full_script_path, 0o755)  # Make it executable
    return full_script_path
