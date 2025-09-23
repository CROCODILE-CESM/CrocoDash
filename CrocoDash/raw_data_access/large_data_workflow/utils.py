import json
import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta


def load_config(config_path: str = "config.json") -> dict:
    """
    Load a JSON config file.

    Parameters
    ----------
    config_path : str, optional
        Path to the JSON config file. Default is "config.json".

    Returns
    -------
    dict
        The loaded configuration as a dictionary.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_config(config: dict, config_path: str = "config.json") -> None:
    """
    Write or update a JSON config file.

    Parameters
    ----------
    config : dict
        Configuration dictionary to save.
    config_path : str, optional
        Path to the JSON config file. Default is "config.json".

    Returns
    -------
    None
    """
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, sort_keys=True)


def parse_dataset_folder(
    folder: str | Path, input_dataset_regex: str, date_format: str
):
    """
    Parse a folder to find and extract dataset file information based on a regex pattern.

    Parameters
    ----------
    folder : str or Path
        Path to the folder containing the dataset files.
    input_dataset_regex : str
        Regular expression pattern to match dataset filenames.
        Example: `"(north|east|south|west)_unprocessed\\.(\\d{8})_(\\d{8})\\.nc"`
    date_format : str
        Date format string used to parse dates in filenames (e.g., "%Y%m%d").

    Returns
    -------
    dict
        Dictionary mapping boundaries to a list of tuples with:
        - Start date (`datetime`)
        - End date (`datetime`)
        - Full file path (`Path`)

        Example:
        {
            "north": [(datetime(2000, 1, 1), datetime(2000, 1, 2), Path("/path/to/north_20000101_20000102.nc"))],
            "east": [(datetime(2000, 1, 3), datetime(2000, 1, 4), Path("/path/to/east_20000103_20000104.nc"))]
        }

    """
    # Dictionary to store boundary info
    boundary_file_list = defaultdict(list)

    # Regex Pattern for the dataset
    pattern = re.compile(input_dataset_regex)

    # Iterate through the folder provided for dataset files
    for file in os.listdir(folder):

        # Get File Path
        file_path = os.path.join(folder, file)

        # Check if file matches
        match = pattern.match(file)
        if match:

            # Extract information
            boundary, start_date, end_date = match.groups()

            # Convert dates to datetime objects
            start_date = datetime.strptime(start_date, date_format)
            end_date = datetime.strptime(end_date, date_format)

            # Append (file path, start date, end date)
            boundary_file_list[boundary].append((start_date, end_date, file_path))

    # Sort the date ranges for each boundary
    for boundary in boundary_file_list:
        boundary_file_list[boundary].sort()

    return boundary_file_list

def check_date_continuity(boundary_file_list: dict):
    """
    Check for overlaps or missing dates between consecutive files.
    """
    issues = defaultdict(list)

    for boundary, files in boundary_file_list.items():
        for (prev_start, prev_end, prev_file), (next_start, next_end, next_file) in zip(files, files[1:]):
            # Expect next_start == prev_end + 1 day
            expected_next = prev_end + timedelta(days=1)
            if next_start < expected_next:
                issues[boundary].append(
                    f"Overlap: {prev_file} ({prev_start:%Y-%m-%d} → {prev_end:%Y-%m-%d}) "
                    f"and {next_file} ({next_start:%Y-%m-%d} → {next_end:%Y-%m-%d})"
                )
            elif next_start > expected_next:
                issues[boundary].append(
                    f"Gap: {prev_file} ends {prev_end:%Y-%m-%d}, "
                    f"next {next_file} starts {next_start:%Y-%m-%d}"
                )

    return issues
