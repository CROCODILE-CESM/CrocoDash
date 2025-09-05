"""
This file takes in a dictionary of variable names and their corresponding file paths, combines them all into one file, and subsets the dataset based on the provided variable names to a provided rectangle
"""

from pathlib import Path
import xarray as xr
import cftime


def subset_dataset(
    variable_info: dict,
    output_path: str | Path,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    lat_name="lat",
    lon_name="lon",
    preview: bool = False,
) -> None:
    """
    Subsets (and merges) the dataset based on the provided variable names and geographical bounds into the output path
    Args:
        variable_info (dict): A dictionary with variable names as keys and their file paths as values.
        output_path (str | Path): The path where the subsetted dataset will be saved.
        lat_min (float): Minimum latitude for subsetting.
        lat_max (float): Maximum latitude for subsetting.
        lon_min (float): Minimum longitude for subsetting.
        lon_max (float): Maximum longitude for subsetting.
        lat_name (str): Name of the latitude variable in the dataset. Default is "lat".
        lon_name (str): Name of the longitude variable in the dataset. Default is "lon".
        preview (bool): If True, only previews the subsetting without saving. Default is False.
    """

    # Create the output directory if it does not exist
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Iterate through each variable and its corresponding file paths
    for var_name, file_paths in variable_info.items():
        output_file = output_path / f"{var_name}_subset.nc"
        if output_file.exists():
            print(f"Subset already exists for {var_name}, skipping")
            continue
        if not file_paths:
            print(f"No files found for variable: {var_name}")
            continue

        # Load the dataset for the variable
        ds = xr.open_mfdataset(file_paths)

        # Convert time. Saving to netcdf is not working with cftime objects
        units = "days since 1850-01-01 00:00:00"
        calendar = "noleap"
        numeric_time = cftime.date2num(ds.time, units=units, calendar=calendar)
        ds = ds.assign_coords(
            time=("time", numeric_time, {"units": units, "calendar": calendar})
        )

        # Drop the time_bound variable, cftime isn't playing well, eventually this should be converted in the same way.
        ds = ds.drop_vars("time_bound")
        mask = (
            (ds[lat_name] >= lat_min - 1)
            & (ds[lat_name] <= lat_max + 1)
            & (ds[lon_name] >= lon_min - 1)
            & (ds[lon_name] <= lon_max + 1)
        )
        mask = mask.compute()

        # Subset the dataset based on the provided geographical bounds
        if not preview:
            subset_ds = ds.where(mask, drop=True)

            # Save the subsetted dataset to the output path
           
            subset_ds.to_netcdf(output_file)

            print(f"Subsetted dataset for variable '{var_name}' saved to {output_file}")

    return


if __name__ == "__main__":
    print(
        "This script is used to subset the large datasets based on variable names and geographical bounds."
    )
