from datetime import datetime
import xarray as xr
from CrocoDash import utils
from CrocoDash.raw_data_access.large_data_workflow.utils import (
    load_config,
    parse_dataset_folder,
    check_date_continuity
)
from pathlib import Path
from collections import defaultdict
import shutil

logger = utils.setup_logger(__name__)


def merge_piecewise_dataset(
    folder: str | Path,
    input_dataset_regex: str,
    date_format: str,
    start_date: str,
    end_date: str,
    boundary_number_conversion: dict,
    output_folder: str | Path,
    run_initial_condition: bool = True,
    preview: bool = False,
):
    """
    Merges piecewise datasets from a folder into consolidated NetCDF files by boundary.

    Parameters
    ----------
    folder : str or Path
        Path to the folder containing the regridded dataset files.
    input_dataset_regex : str
        Regular expression pattern to match dataset files.
    date_format : str
        Date format string used for parsing the dataset filenames.
    start_date : str
        Start date in the specified format.
    end_date : str
        End date in the specified format.
    boundary_number_conversion : dict
        Dictionary mapping boundary segment numbers to their labels.
    output_folder : str or Path
        Directory to save the merged NetCDF files.
    run_initial_condition: bool
        Whether to run initial condition, default is true.
    preview : bool, optional
        Whether to run in preview mode without saving (default is False).

    Raises
    ------
    ValueError
        If a segment in `boundary_number_conversion` is not found in the dataset folder.

    Returns
    -------
    None
        Saves the merged NetCDF files to the specified output folder.
    """
    logger.info("Parsing Regridded Data Folder")
    folder = Path(folder)

    # Parse data folder and find required files
    start_date = datetime.strptime(start_date, date_format)
    end_date = datetime.strptime(end_date, date_format)
    boundary_file_list = parse_dataset_folder(folder, input_dataset_regex, date_format)
    inverted_bnc = {v: k for k, v in boundary_number_conversion.items()}
    boundary_list = boundary_file_list.keys()
    issues = check_date_continuity(boundary_file_list)
    if issues:
        for boundary, msgs in issues.items():
            for m in msgs:
                logger.warning("[%s] %s", boundary, m)
    else:
        logger.info("All boundaries continuous and non-overlapping.")

    for seg_num in inverted_bnc:
        if not any(f"{seg_num:03}" in boundary for boundary in boundary_list):
            raise ValueError(
                f"Segment Number '{seg_num}' from boundary_number_conversion not found in the available boundary files. Did you correctly regrid the right boundaries? Change the boundary number conversion to match."
            )

    matching_files = defaultdict(list)
    for boundary in boundary_list:
        for file_start, file_end, file_path in boundary_file_list[boundary]:
            if file_start <= end_date and file_end >= start_date:
                matching_files[boundary].append(file_path)

    # Merge Files
    logger.info("Merging Files")
    output_file_names = []
    for boundary in boundary_list:
        output_file_name = f"forcing_obc_segment_{boundary}.nc"
        output_path = Path(output_folder) / output_file_name
        output_file_names.append(output_file_name)
        if not preview:
            ds = xr.open_mfdataset(
                matching_files[boundary],
                combine="nested",
                concat_dim="time",
                coords="minimal",
            )
            ds.to_netcdf(output_path)
            ds.close()
            logger.info(f"Saved {boundary} boundary at {output_path}")
    # Copy Initial Condition
    if run_initial_condition:
        ic_files_to_copy = [
            folder / "init_eta.nc",
            folder / "init_vel.nc",
            folder / "init_tracers.nc",
        ]
        for file_path in ic_files_to_copy:
            shutil.copy(file_path, Path(output_folder))
            matching_files["IC"].append(str(file_path))
        output_file_names.append("init_eta.nc")
        output_file_names.append("init_vel.nc")
        output_file_names.append("init_tracers.nc")
    if preview:
        return {
            "matching_files": matching_files,
            "output_folder": output_folder,
            "output_file_names": output_file_names,
        }


def main(config_path):
    config = load_config(config_path)
    merge_piecewise_dataset(
        config["paths"]["raw_dataset_path"],
        config["raw_file_regex"]["regridded_dataset_pattern"],
        config["dates"]["format"],
        config["dates"]["start"],
        config["dates"]["end"],
        config["boundary_number_conversion"],
        config["paths"]["merged_dataset_path"],
    )
    return


if __name__ == "__main__":
    main("<CONFIG FILEPATH>")
