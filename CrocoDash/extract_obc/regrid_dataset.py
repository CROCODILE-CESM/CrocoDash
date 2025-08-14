"""
Regrid the datasets to a specified grid using regional_mom6 tools and xesmf
"""

from regional_mom6 import regridding as rgd
import xarray as xr
import json

REGRID_ITEMS = ["IC", "west", "south", "north", "east"]


def create_regridders(    input_path: str | Path,
    output_path: str | Path,
    supergrid: xr.Dataset,
    variable_info: dict,
    lat_name: str = "lat",
    lon_name: str = "lon") -> dict:
    """
    Return Regridders for each boundary using regional_mom6 tools.
    """
    hgrid = supergrid
    # Create regridders for each boundary
    variable_to_use = variable_info.keys()[0]
    regridders = {}
    ds = xr.open_dataset(input_path/f"{variable_to_use}_subset.nc")
    ds["lon"] = ds[lon_name]
    ds["lat"] = ds[lat_name]
    hgrid["lon"] = hgrid["x"]
    hgrid["lat"] = hgrid["y"]
    for item in REGRID_ITEMS:
        print(f"Creating regridder for {item}")
        if item == "IC":
            # Initial Condition must be handled seperately in 2D
            
            regridders[item] = rgd.create_regridder(
                ds[["lon", "lat", variable_to_use]],
                hgrid,
                locstream_out = False,
                outfile = output_path/f"{item}_weights.nc"
            )
        else:
            coords = rgd.coords(hgrid, item, "segment_{:03d}".format(boundary_number_conversion[item]))
            regridders[item] = rgd.create_regridder(
                ds[["lon", "lat", variable_to_use]],
                coords,
                locstream_out = True,
                outfile = f"output_path/{item}_weights.nc"
            )
    return regridders

def regrid_dataset_to_boundaries(
    input_path: str | Path,
    output_path: str | Path,
    supergrid: xr.Dataset,
    variable_info: dict,
    lat_name: str = "lat",
    lon_name: str = "lon",
    preview = False
):
    """
    Regrid the datasets to specified boundaries using regional_mom6 tools.

    Args:
        input_path (str | Path): Path to the input dataset.
        output_path (str | Path): Path to save the regridded dataset.
        supergrid (xr.Dataset): The supergrid dataset to regrid onto.
        variable_info (dict): Dictionary containing variable names and their file paths.
    """

    # Make sure the paths is a Path object and exists
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    if not input_path.exists():
        raise ValueError(f"Input path {input_path} does not exist.")

    regridders = create_regridders(input_path, output_path, supergrid, variable_info, lat_name, lon_name)

    output_paths = []

    # Regrid and save the datasets
    for item in REGRID_ITEMS:
        for v in variable_info:
            try:
                print(f"Regridding {v} {item}")
                input_file = input_path/f"{v}_subset.nc"
                output_file = output_path/f"{v}_{item}_regridded.nc"
                with xr.open_dataset(input_file, chunks="auto") as ds:
                    ds = ds.rename({lon_name: "lon", lat_name: "lat"})
                    
                    # Perform regridding
                    if not preview:
                        regridded = regridders[item](ds[v])
                    
                    # Save regridded dataset
                    regridded.to_netcdf(output_file)
                    regridded.close()
                    output_paths.append(str(output_file.resolve()))

                print(f"{v} {item} regridded")

            except Exception as e:
                print(f"Failed to regrid {v} {item}: {e}")
    
    return output_paths


