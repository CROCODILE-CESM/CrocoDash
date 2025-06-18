from pathlib import Path
from CrocoDash import utils
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info
from CrocoDash.raw_data_access.utils import load_config
from CrocoDash.raw_data_access import driver as dv
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta

logger = utils.setup_logger(__name__)


def get_dataset_piecewise(
    product_name: str,
    function_name: str,
    date_format: str,
    start_date: str,
    end_date: str,
    hgrid_path: str | Path,
    step_days: int,
    output_dir: str | Path,
    boundary_number_conversion: dict,
    run_initial_condition: bool = True,
    preview: bool = False,
):
    """
    Retrieves and saves data in piecewise chunks for each boundary over a date range.

    Parameters
    ----------
    product_name : str
        The name of the data product to retrieve.
    function_name : str
        The function to call for retrieving data.
    date_format : str
        The date format string (e.g., "%Y-%m-%d").
    start_date : str
        The start date in the specified format.
    end_date : str
        The end date in the specified format.
    hgrid_path : str or Path
        Path to the hgrid file containing the regional grid.
    step_days : int
        The number of days in each data chunk.
    output_dir : str or Path
        The directory to save the output NetCDF files.
    boundary_number_conversion : dict
        Dictionary mapping boundaries to their numerical identifiers.
    run_initial_condition : bool
        Whether or not to run the initial condition, default is true
    preview : bool
        Whether or not to preview the run, default is false

    Raises
    ------
    ValueError
        If the product or function is not found in the registry.

    Returns
    -------
    None
        Saves the retrieved data to the specified output directory.
    """
    # Create the output directory if it doesn't exist
    Path(output_dir).mkdir(exist_ok=True)

    ## Initialize PFD
    ProductFunctionRegistry = dv.ProductFunctionRegistry()
    ProductFunctionRegistry.load_functions()
    ProductFunctionRegistry.validate_function(product_name, function_name)
    data_access_function = ProductFunctionRegistry.functions[product_name][
        function_name
    ]

    # Get lat,lon information for each boundary
    hgrid = xr.open_dataset(hgrid_path)
    boundary_info = get_rectangular_segment_info(hgrid)

    # Set up date range, pd.date_range is exclusive of the end_date
    dates = (
        pd.date_range(start=start_date, end=end_date, freq=f"{step_days}D")
        .to_pydatetime()
        .tolist()
    )

    # Add the end date manually if not included
    if dates[-1] != datetime.strptime(end_date, date_format):
        dates.append(datetime.strptime(end_date, date_format))

    num_files = len(dates) - 1

    logger.info(
        f"Downloading {product_name} data using {function_name} from {dates[0]} to {dates[-1]}."
    )
    logger.info(
        f"Using step size {step_days}, this will result in {num_files} files per boundary."
    )

    # Set up the first start_date starter
    start_date = dates[0]
    output_file_names = []
    # Retrieve and save data piecewise
    for ind in range(len(dates) - 1):
        end_date = dates[ind + 1]
        start_date_str = start_date.strftime(date_format)
        end_date_str = end_date.strftime(date_format)

        # Set Initial Condition
        if run_initial_condition and ind == 0:
            latlon_info = boundary_info["ic"]
            output_file = f"ic_unprocessed.nc"
            output_file_names.append(output_file)
            end_ic_date = start_date + timedelta(days=1)
            end_ic_date_str = end_ic_date.strftime(date_format)

            # Execute the data retrieval function
            if not preview:
                data_access_function(
                    dates=[start_date_str, end_ic_date_str],
                    lat_min=latlon_info["lat_min"],
                    lat_max=latlon_info["lat_max"],
                    lon_min=latlon_info["lon_min"],
                    lon_max=latlon_info["lon_max"],
                    output_dir=output_dir,
                    output_file=output_file,
                )

        for boundary in boundary_number_conversion.keys():

            latlon_info = boundary_info[boundary]
            output_file = f"{boundary}_unprocessed.{start_date_str}_{end_date_str}.nc"
            output_file_names.append(output_file)
            # Execute the data retrieval function
            if not preview:
                data_access_function(
                    dates=[start_date_str, end_date_str],
                    lat_min=latlon_info["lat_min"],
                    lat_max=latlon_info["lat_max"],
                    lon_min=latlon_info["lon_min"],
                    lon_max=latlon_info["lon_max"],
                    output_dir=output_dir,
                    output_file=output_file,
                )

        start_date = end_date + timedelta(days=1)

    if not preview:
        logger.info(
            f"Successfully retrieved {product_name} data located in {output_dir} directory."
        )
    if preview:
        return {
            "dates": dates,
            "output_file_names": output_file_names,
            "output_folder": output_dir,
        }


def main(config_file):
    """
    Main function to run the large dataset workflow using a configuration file.

    Parameters
    ----------
    config_file : str or Path
        Path to the configuration JSON file.

    Returns
    -------
    None
    """
    print("Starting Large Dataset Workflow")
    config = load_config(config_file)

    ## Check to make sure everything exists INCOMPLETE
    get_dataset_piecewise(
        product_name=config["forcing"]["product_name"],
        function_name=config["forcing"]["function_name"],
        date_format=config["dates"]["format"],
        start_date=config["dates"]["start"],
        end_date=config["dates"]["end"],
        hgrid_path=config["paths"]["hgrid_path"],
        step_days=int(config["params"]["step"]),
        output_dir=config["paths"]["raw_dataset_path"],
        boundary_number_conversion=config["boundary_number_conversion"],
        run_initial_condition=True,
        preview=config["params"]["preview"],
    )


if __name__ == "__main__":
    main("<CONFIG FILEPATH>")
