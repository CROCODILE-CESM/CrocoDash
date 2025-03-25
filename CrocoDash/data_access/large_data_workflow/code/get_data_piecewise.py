from pathlib import Path
from CrocoDash import utils
from CrocoDash.data_access.driver import get_rectangular_segment_info
from CrocoDash.data_access.utils import load_config
import CrocoDash.data_access.datasets as datasets
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
    output_dataset_regex: str, # haven't figured out how to process this for output
    date_format: str,
    start_date: str,
    end_date: str,
    hgrid_path: str | Path,
    dataset_varnames: dict,
    step_days: int, # step increment for chunking data
    output_dir: str | Path,
    boundary_number_conversion: dict, # doesn't need to be the full dict, but we need to know which boundaries to get
):
    
    ## Get function from datasets module
    module = importlib.import_module(
                    "." + product_name, package="CrocoDash.data_access.datasets"
                )
    func = getattr(module, function_name)
    
    ## Get lat,lon information for each boundary
    hgrid = xr.open_dataset(hgrid_path)
    boundary_info = get_rectangular_segment_info(hgrid)
    
    ## Check step size makes sense
    if step_days <= 0:
        raise ValueError("step_days must be a positive integer.")
    
    ## Set up date range, without step size (a little clunky, could be changed)
    dates = pd.date_range(start=start_date, end=end_date).to_pydatetime().tolist()
    print("TODO - Look into pd.date_range freq argument, does it catch remainder??")
    print("TODO – Chunking Dates is done separately right now, probably not great.")
    date_strings = [date.strftime(date_format) for date in dates]
    
    num_files = (len(dates)+step_days-1)//step_days # ceiling division of number of days with step_days
    
    ## Grab dates step_days number of days at a time
    date_ranges = [[date_strings[i], date_strings[i+4]] for i in range(0,len(date_strings)-step_days,step_days)]
    remaining_days = len(dates)%step_days # Get any remainder
    if (remaining_days != 0):
        date_ranges.append([date_strings[-remaining_days],date_strings[-1]]) # definitely not the best way to do this
        
    # DEV: Check that it returns the expected number of date ranges
    assert(len(date_ranges)==num_files),"DEV_ERROR: Error with date_ranges in get_glorys_rda_piecewise"
    
    logger.info(f"Downloading {product_name} data using {function_name} from {dates[0]} to {dates[-1]}.")
    logger.info(f"Using step size {step_days}, this will result in {num_files} total files.")
    
    for date_range in date_ranges:
        for boundary in boundary_number_conversion.keys(): 
            ## Ideally we do the boundary parsing in get_glorys_from_rda for memory and open/closing efficiency
            latlon_info = boundary_info[boundary]
            output_file = f"{boundary}_unprocessed.{date_range[0]}_{date_range[1]}.nc"
            # dataset_var_values = pd.json_normalize(dataset_varnames)
            
            # assert(re.match(output_dataset_regex),output_file)
            
            path = func(
                dates = date_range, 
                lat_min = latlon_info["lat_min"],
                lat_max = latlon_info["lat_max"],
                lon_min = latlon_info["lon_min"],
                lon_max = latlon_info["lon_max"],
                output_dir = output_dir,
                output_file = output_file,
                dataset_varnames = list(dataset_varnames.values())
                )
        
    logger.info(f"Successfull retrieved (probably, if there were no angry red errors) {product_name} data located in {output_dir} directory.")
    

def main(config_file):
    print("Starting Large Dataset Workflow")
    config = load_config(config_file)
    
    ## Check to make sure everything exists INCOMPLETE
    get_data_piecewise(
    product_name=config['forcing']['product_name'],
    function_name=config['forcing']['function_name'],
    output_dataset_regex=config['raw_file_regex']['raw_dataset_pattern'], # haven't figured out how to process this for output
    date_format=config['dates']['format'],
    start_date=config['dates']['start'],
    end_date=config['dates']['end'],
    hgrid_path=config['paths']['hgrid_path'],
    dataset_varnames=config['forcing']['varnames'],
    step_days=int(config['params']['step']), # step increment for chunking data
    output_dir=config['paths']['raw_dataset_path'],
    boundary_number_conversion=config['boundary_number_conversion'], # doesn't need to be the full dict, but we need to know which boundaries to get
    )
    
    
    
if __name__ == "__main__":
    config_file = '/glade/work/ajanney/DataAccess/Large_Data_Workflow/get_data_pieces/config.json'
    main(config_file)