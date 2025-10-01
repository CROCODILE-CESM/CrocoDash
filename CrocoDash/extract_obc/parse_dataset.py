"""
This script is used to load CESM datasets and extract all the necessary information for OBC generation. So, it takes in a variable name(s) and dataset path, finds all files related to the variable(s).
It then outputs a dictionary with the variable name(s) and their corresponding file paths.
"""

import xarray as xr
from pathlib import Path
from dateutil import parser
import os
import re
from datetime import datetime


def parse_dataset(
    variable_names: list[str],
    dataset_path: str | Path,
    start_date: str,
    end_date: str,
    date_format: str = "%Y%m%d",
    regex=r"(\d{6,8})-(\d{6,8})",
    space_character=".",
) -> dict:
    """
    Parses the dataset to find variable names and their corresponding file paths.

    Args:
        variable_names (list[str]): List of variable names to search for.
        dataset_path (str | xr.Dataset | Path): Path to the dataset (or folder with dataset)
        space_character (str): Character that separates words in variable names in the filenames. Default is ".".

    Returns:
        dict: A dictionary with variable names as keys and their file paths as values.
    """
    print("Parsing dataset...")
    start_date = parser.parse(start_date)
    end_date = parser.parse(end_date)
    # Create a dictionary to hold variable names and their file paths
    variable_info = {}
    for v in variable_names:
        variable_info[v] = []

    dataset_path = Path(dataset_path)
    if dataset_path.is_dir():
        for file_path in dataset_path.rglob("*"):
            if file_path.is_file():
                # Check each variable
                for v in variable_names:
                    if (space_character + v + space_character) in str(
                        file_path
                    ):  # check full path, not just name
                        s = str(file_path.resolve())
                        dt1, dt2 = get_date_range_from_filename(s, regex)
                        if (dt1 >= start_date and dt1 <= end_date) or (
                            dt2 >= start_date and dt2 <= end_date
                        ):
                            variable_info[v].append(s)

    elif dataset_path.is_file():
        for v in variable_names:
            variable_info[v] = [str(dataset_path.resolve())]
    else:
        raise ValueError("dataset_path must be a string, Path to existing file(s)")

    # Print the found file paths
    for v in variable_info:
        print(f"{len(variable_info[v])} file(s) found for variable '{v}'")

    return variable_info


def get_date_range_from_filename(path, regex):
    fname = os.path.basename(path)
    m = re.search(regex, fname)
    if not m:
        return None

    def parse_date(datestr):
        if len(datestr) == 6:  # YYYYMM
            return datetime.strptime(datestr, "%Y%m")
        elif len(datestr) == 8:  # YYYYMMDD
            return datetime.strptime(datestr, "%Y%m%d")
        else:
            raise ValueError(f"Unexpected date format: {datestr}")

    start = parse_date(m.group(1))
    end = parse_date(m.group(2))
    return start, end


if __name__ == "__main__":
    print(
        "This script is used to load CESM datasets and extract all the necessary information for OBC generation "
    )
