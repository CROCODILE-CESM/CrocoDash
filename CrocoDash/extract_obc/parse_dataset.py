"""
This script is used to load CESM datasets and extract all the necessary information for OBC generation. So, it takes in a variable name(s) and dataset path, finds all files related to the variable(s). 
It then outputs a dictionary with the variable name(s) and their corresponding file paths.
"""

import xarray as xr
from pathlib import Path


def parse_dataset(variable_names: list[str], dataset_path: str | Path) -> dict:
    """
    Parses the dataset to find variable names and their corresponding file paths.

    Args:
        variable_names (list[str]): List of variable names to search for.
        dataset_path (str | xr.Dataset | Path): Path to the dataset (or folder with dataset)

    Returns:
        dict: A dictionary with variable names as keys and their file paths as values.
    """
    variable_info = {}
    for v in variable_names:
        variable_info[v] = []
        dataset_path = Path(dataset_path)
    if dataset_path.is_dir():
        for file_path in dataset_path.rglob("*"):
            if file_path.is_file():
                # Check each variable
                for v in variable_names:
                    if v in str(file_path):  # check full path, not just name
                        variable_info[v].append(str(file_path.resolve()))

    elif dataset_path.is_file():
        for v in variable_names:
            variable_info[v] = [str(dataset_path.resolve())]
    else:
        raise ValueError("dataset_path must be a string, Path to existing file(s)")

    result = {}
    for var_name in variable_names:
        if var_name in dataset.variables:
            result[var_name] = str(
                dataset[var_name].encoding.get("source", "Unknown source")
            )

    return result


if __name__ == "__main__":
    print(
        "This script is used to load CESM datasets and extract all the necessary information for OBC generation. This dataset "
    )
