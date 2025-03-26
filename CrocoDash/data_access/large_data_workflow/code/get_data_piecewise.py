from pathlib import Path
from CrocoDash import utils
from CrocoDash.data_access.driver import get_rectangular_segment_info
from CrocoDash.data_access.utils import load_config
from CrocoDash.data_access import driver as dv
import importlib
import json
import re
import os
from datetime import datetime
import xarray as xr
import pandas as pd

logger = utils.setup_logger(__name__)


def get_data_piecewise(
    product_name: str,
    function_name: str,
    date_format: str,
    start_date: str,
    end_date: str,
    hgrid_path: str | Path,
    step_days: int,  # step increment for chunking data
    output_dir: str | Path,
    boundary_number_conversion: dict,  # doesn't need to be the full dict, but we need to know which boundaries to get
):

    ## Initialize PFD
    ProductFunctionRegistry = dv.ProductFunctionRegistry()
    ProductFunctionRegistry.load_functions()
    ProductFunctionRegistry.validate_function(product_name, function_name)
    func = ProductFunctionRegistry.functions[product_name][function_name]

    # Get lat,lon information for each boundary
    hgrid = xr.open_dataset(hgrid_path)
    boundary_info = get_rectangular_segment_info(hgrid)

    # Set up date range
    dates = (
        pd.date_range(start=start_date, end=end_date, freq=f"{step_days}D")
        .to_pydatetime()
        .tolist
    )

    # Add the end date manually if not included
    if dates[-1] != pd.to_datetime(end_date):
        dates = dates.append(pd.to_datetime([end_date]))

    date_strings = [date.strftime(date_format) for date in dates]
    num_files = len(date_strings) - 1

    logger.info(
        f"Downloading {product_name} data using {function_name} from {dates[0]} to {dates[-1]}."
    )
    logger.info(
        f"Using step size {step_days}, this will result in {num_files} total files."
    )

    # Calling File Retrieval
    for ind in range(len(date_strings) - 1):
        for boundary in boundary_number_conversion.keys():
            ## Ideally we do the boundary parsing in get_glorys_from_rda for memory and open/closing efficiency
            latlon_info = boundary_info[boundary]
            output_file = (
                f"{boundary}_unprocessed.{date_strings[ind]}_{date_strings[ind+1]}.nc"
            )

            path = func(
                dates=[date_strings[ind], date_strings[ind + 1]],
                lat_min=latlon_info["lat_min"],
                lat_max=latlon_info["lat_max"],
                lon_min=latlon_info["lon_min"],
                lon_max=latlon_info["lon_max"],
                output_dir=output_dir,
                output_file=output_file,
            )

    logger.info(
        f"Successfull retrieved {product_name} data located in {output_dir} directory."
    )


def main(config_file):
    print("Starting Large Dataset Workflow")
    config = load_config(config_file)

    ## Check to make sure everything exists INCOMPLETE
    get_data_piecewise(
        product_name=config["forcing"]["product_name"],
        function_name=config["forcing"]["function_name"],
        date_format=config["dates"]["format"],
        start_date=config["dates"]["start"],
        end_date=config["dates"]["end"],
        hgrid_path=config["paths"]["hgrid_path"],
        step_days=int(config["params"]["step"]),  # step increment for chunking data
        output_dir=config["paths"]["raw_dataset_path"],
        boundary_number_conversion=config[
            "boundary_number_conversion"
        ],  # doesn't need to be the full dict, but we need to know which boundaries to get
    )


if __name__ == "__main__":
    config_file = (
        "/glade/work/ajanney/DataAccess/Large_Data_Workflow/get_data_pieces/config.json"
    )
    main(config_file)
