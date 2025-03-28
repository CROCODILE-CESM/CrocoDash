import regional_mom6 as rm6
from pathlib import Path
from CrocoDash import utils
from CrocoDash.data_access.large_data_workflow.utils import load_config
import re
import os
from collections import defaultdict
from datetime import datetime
import xarray as xr

logger = utils.setup_logger(__name__)


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


def regrid_dataset_piecewise(
    folder: str | Path,
    input_dataset_regex: str,
    date_format: str,
    start_date: str,
    end_date: str,
    hgrid: str | Path,
    dataset_varnames: dict,
    output_folder: str | Path,
    boundary_number_conversion: dict,
    preview: bool = False
):
    """
    Find the required files, set up the necessary data, and regrid the dataset.

    Parameters
    ----------
    folder : str or Path
        Path to the folder containing the dataset files.
    input_dataset_regex : str
        Regular expression pattern to match dataset files.
    date_format : str
        Date format string used to parse dates in filenames (e.g., "%Y%m%d").
    start_date : str
        Start date of the dataset range in `YYYYMMDD` format.
    end_date : str
        End date of the dataset range in `YYYYMMDD` format.
    hgrid : str or Path
        Path to the horizontal grid file used for regridding.
    dataset_varnames : dict
        Mapping of variable names in the dataset to standardized names.
        Example:
        {
            "time": "time",
            "latitude": "yh",
            "longitude": "xh",
            "depth": "zl"
        }
    output_folder : str or Path
        Path to the folder where the regridded dataset will be saved.
    boundary_number_conversion : dict
        Dictionary mapping boundary names to numerical IDs.
        Example:
        {
            "north": 1,
            "east": 2,
            "south": 3,
            "west": 4
        }
    preview :  bool
        Whether or not to preview the run of this function, defaults to false

    Returns
    -------
    None
        The regridded dataset files are saved to the specified `output_folder`.

    """
    logger.info("Parsing Raw Data Folder")
    # Parse data folder and find required files
    start_date = datetime.strptime(start_date, date_format)
    end_date = datetime.strptime(end_date, date_format)
    boundary_file_list = parse_dataset_folder(folder, input_dataset_regex, date_format)

    boundary_list = boundary_file_list.keys()

    for boundary in boundary_list:
        if boundary not in boundary_number_conversion:
            logger.error(
                f"Boundary '{boundary}' not found in the boundary_number_conversion. We need the boundary_number_conversion for all boundaries to identify what number to label each segment."
            )
            return

    matching_files = defaultdict(list)
    for boundary in boundary_list:
        for file_start, file_end, file_path in boundary_file_list[boundary]:
            if file_start <= end_date and file_end >= start_date:
                matching_files[boundary].append((file_start, file_end, file_path))

    logger.info("Setting up required information")
    # Setup required information for regridding

    # Read in hgrid
    hgrid = xr.open_dataset(hgrid)

    # Set up required information
    expt = rm6.experiment.create_empty()
    expt.hgrid = hgrid
    expt.mom_input_dir = Path(output_folder)
    expt.date_range = [start_date, None]

    logger.info("Starting regridding")
    output_file_names = []
    # Do Regridding
    for boundary in matching_files.keys():
        for file_start, file_end, file_path in matching_files[boundary]:
            file_path = Path(file_path)
            if not preview:
                expt.setup_single_boundary(
                    file_path,
                    dataset_varnames,
                    boundary,
                    boundary_number_conversion[boundary],
                )

            # Rename output file
            output_file_path = (
                expt.mom_input_dir
                / "forcing_obc_segment_{:03d}.nc".format(
                    boundary_number_conversion[boundary]
                )
            )

            # Rename file
            boundary_str = f"{boundary_number_conversion[boundary]:03d}"
            file_start_date = file_start.strftime(date_format)
            file_end_date = file_end.strftime(date_format)
            filename_with_dates = "forcing_obc_segment_{}_{}_{}.nc".format(
                boundary_str, file_start_date, file_end_date
            )
            output_file_names.append(filename_with_dates)
            output_file_path_with_dates = expt.mom_input_dir / filename_with_dates
            if not preview:
                logger.info(f"Saving regridding file as {filename_with_dates}")
            os.rename(output_file_path, output_file_path_with_dates)
    if not preview:
        logger.info("Finished regridding")
        return
    elif preview:
        return {
            "matching_files": matching_files,
            "output_folder": expt.mom_input_dir,
            "output_file_names": output_file_names
        }


def main(config_path):
    config = load_config(config_path)
    regrid_dataset_piecewise(
        config["paths"]["raw_dataset_path"],
        config["raw_file_regex"]["raw_dataset_pattern"],
        config["dates"]["format"],
        config["dates"]["start"],
        config["dates"]["end"],
        config["paths"]["hgrid_path"],
        config["varnames"],
        config["paths"]["output_path"],
        config["boundary_number_conversion"],
        config["params"]["preview"]
    )
    return


if __name__ == "__main__":
    main(
        "/glade/u/home/manishrv/documents/croc/dev/large_data_access/regrid_data_piecewise/config.json"
    )
