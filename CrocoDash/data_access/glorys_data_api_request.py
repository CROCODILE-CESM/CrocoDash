import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import argparse
from CrocoDash.data_access.glorys import get_glorys_data_from_cds_api


def process_glorys_data(args):
    # Convert dates to datetime objects
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
    boundary_name = args.state_file_boundary_name
    lon_min = args.lon_min
    lon_max =args.lon_max
    lat_min = args.lat_min
    lat_max = args.lat_max
    output_dir = args.output_dir
        # Validate date range
    if start_date >= end_date:
        raise ValueError("Start date must be before end date.")

    # Print the parsed arguments
    print("Processing data with the following parameters:")
    print(f"State File Boundary Name: {args.boundary_name}")
    print(f"Start Date: {start_date}")
    print(f"End Date: {end_date}")
    print(f"Longitude Range: {args.lon_min} to {args.lon_max}")
    print(f"Latitude Range: {args.lat_min} to {args.lat_max}")

    # Define the state file
    state_file = os.path.join(output_dir, boundary_name+"_state.txt")

    # Initialize the state file if it doesn't exist
    if not os.path.exists(state_file):
        with open(state_file, "w") as f:
            f.write(f"last_successful_date={start_date.strftime("%Y-%m-%d")}\n")

    # Read the last successful date from the state file
    with open(state_file, "r") as f:
        last_successful_date_str = f.readline().strip().split("=")[1]
    last_successful_date = datetime.strptime(last_successful_date_str, "%Y-%m-%d")

    # Loop through each month
    current_date = last_successful_date
    while current_date <= end_date:
        next_date = current_date + relativedelta(months=1)
        next_date = next_date.replace(day=1)

        # Define the parameters for the data download
        params = {
            "dataset_id": "cmems_mod_glo_phy_my_0.083deg_P1D-m",
            "variables": ["so", "thetao", "uo", "vo", "zos"],
            "start_datetime": current_date.strftime("%Y-%m-%dT00:00:00"),
            "end_datetime": next_date.strftime("%Y-%m-%dT00:00:00"),
            "lon_min": lon_min,
            "lon_max": lon_max,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "output_dir": output_dir,
            "output_file": f"east_unprocessed_{current_date.strftime('%Y%m')}.nc",
        }
        print("Processing data for", current_date.strftime("%Y-%m-%d"))
        # Execute the data download
        try:
            get_glorys_data_from_cds_api(**params)
            # Update the state file with the current date
            with open(state_file, "w") as f:
                f.write(f"last_successful_date={current_date.strftime('%Y-%m-%d')}\n")
        except Exception as e:
            print(
                f"Failed to process data for {current_date.strftime('%Y-%m-%d')}. Error: {e}"
            )
            break

        # Move to the next month
        current_date = next_date

def main():
    # Define command-line arguments
    parser = argparse.ArgumentParser(description="Process geographical data.")
    parser.add_argument("--boundary_name", type=str, required=True, help="Boundary name (e.g., 'east').")
    parser.add_argument("--start_date", type=str, required=True, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end_date", type=str, required=True, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--lon_min", type=float, required=True, help="Minimum longitude value.")
    parser.add_argument("--lon_max", type=float, required=True, help="Maximum longitude value.")
    parser.add_argument("--lat_min", type=float, required=True, help="Minimum latitude value.")
    parser.add_argument("--lat_max", type=float, required=True, help="Maximum latitude value.")
    parser.add_argument("--output_dir", type=str, required=True, help="Directory where the output files will be saved.")

    # Parse arguments
    args = parser.parse_args()

    # Validate output directory
    if not os.path.isdir(args.output_dir):
        raise ValueError(f"Output directory does not exist: {args.output_dir}")

    # Process the data
    try:
        process_glorys_data(args)
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()