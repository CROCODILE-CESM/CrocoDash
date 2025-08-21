"""
This script is used to load the regridded datasets on a regional supergrid and format them into the required structure for MOM6
"""

from regional_mom6 import regridding as rgd
import xarray as xr
import json
from pathlib import Path
import numpy as np

REGRID_ITEMS = ["IC", "west", "south", "north", "east"]


def format_dataset(
    input_path: str | Path,
    output_path: str | Path,
    supergrid: xr.Dataset,
    bathymetry: xr.Dataset,
    variable_info: dict,
    lat_name: str = "lat",
    lon_name: str = "lon",
    z_dim: str = "z_t",
    preview: bool = False,
) -> dict:
    """
    Format the dataset to MOM6 formats

    Args:
        input_path (str | Path): Path to the input dataset.
        output_path (str | Path): Path where the formatted dataset will be saved.
        supergrid (xr.Dataset): The supergrid dataset to regrid onto.
        bathymetry (xr.Dataset): Bathymetry dataset for masking.
        variable_info (dict): Dictionary containing variable names and their file paths.
        lat_name (str): Name of the latitude variable in the dataset. Default is "lat".
        lon_name (str): Name of the longitude variable in the dataset. Default is "lon".
        preview (bool): If True, only previews the regridding without saving. Default is False.

    Returns:
        dict: Paths to the output files for each boundary.
    """
    # Make sure the paths is a Path object and exists
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    if not input_path.exists():
        raise ValueError(f"Input path {input_path} does not exist.")

    # Start formatting
    output_paths = []
    for v in variable_info:
        for item in REGRID_items:
            # Open Dataset
            ds = xr.open_dataset(input_path / f"{v}_{item}_regridded.nc")
            if item is not "ic":
                segment_name = "segment_{:03d}".format(boundary_number_conversion[item])
                file_path = output_path / f"{v}_obc_{segment_name}.nc"
                if file_path.exists():
                    print(f"Already processed {v} {item}, skipping!")
                    continue

                ## Apply Unit Conversion if needed

                dim_name = ds.variables["__xarray_dataarray_variable__"].dims[-1]
                coords = rgd.coords(hgrid, item, segment_name)
                ds[v] = ds.__xarray_dataarray_variable__
                ds = ds.drop_vars(["__xarray_dataarray_variable__"])
                ds = ds.rename(
                    {"lon": f"lon_{segment_name}", "lat": f"lat_{segment_name}"}
                )
                item_name = f"{v}_{segment_name}"
                ds = ds.rename({v: item_name})

                if z_dim not in ds[v].dims:
                    print(
                        "This variable is only a surface variable, skipping z_dim conversion."
                    )
                    z_dim = None
                else:
                    ds = rgd.vertical_coordinate_encoding(
                        ds, item_name, segment_name, z_dim
                    )
                    ds = rgd.generate_layer_thickness(
                        ds, item_name, segment_name, z_dim
                    )

                ds[item_name] = rgd.fill_missing_data(
                    ds[item_name],
                    xdim=dim_name,
                    zdim=z_dim,
                )
                ds = rgd.add_secondary_dimension(ds, item_name, coords, segment_name)
                # Overwrite actual lat/lon vals with grid numbers in these variables
                ds[f"{coords.attrs['parallel']}_{segment_name}"] = np.arange(
                    ds[f"{coords.attrs['parallel']}_{segment_name}"].size
                )
                ds[f"{coords.attrs['perpendicular']}_{segment_name}"] = [0]
                ds = ds.drop_vars([v])

                ds = rgd.mask_dataset(
                    ds,
                    bathymetry,
                    segment,
                    y_dim_name="lath",
                    x_dim_name="lonh",
                )
                # Do Encoding
                encoding_dict = {
                    "time": {"dtype": "double", "_FillValue": 1.0e2},
                    f"nx_{segment_name}": {
                        "dtype": "int32",
                    },
                    f"ny_{segment_name}": {
                        "dtype": "int32",
                    },
                }

                encoding_dict = rgd.generate_encoding(
                    ds,
                    encoding_dict,
                    default_fill_value=1.0e2,
                )

                # Save File Out
                output_paths.append(file_path)
                ds.load().to_netcdf(
                    file_path,
                    encoding=encoding_dict,
                    unlimited_dims="time",
                )
                print(f"....Finished {v} {segment} processing!")
            else:
                file_path = out_folder / f"{v}_ic.nc"
                if file_path.exists():
                    print(f"Already processed {v}, skipping!")
                    continue
                # Slice the velocites to the u and v grid.
                u_points = rgd.get_hgrid_arakawa_c_points(hgrid, "u")
                v_points = rgd.get_hgrid_arakawa_c_points(hgrid, "v")
                t_points = rgd.get_hgrid_arakawa_c_points(hgrid, "t")

                ds[v] = ds.__xarray_dataarray_variable__

                # Drop old var
                ds = ds.drop_vars(["__xarray_dataarray_variable__"])

                # Fill Missing Data
                if z_dim not in ds[v].dims:
                    z_dim = None

                ds[v] = rgd.fill_missing_data(
                    ds[v],
                    xdim="lon",
                    zdim=z_dim,
                )

                # Do Encoding
                encoding_dict = {
                    "time": {"dtype": "double", "_FillValue": 1.0e2},
                }

                encoding_dict = rgd.generate_encoding(
                    ds,
                    encoding_dict,
                    default_fill_value=1.0e2,
                )

                # Save File Out
                output_paths.append(file_path)
                ds.load().to_netcdf(
                    file_path,
                    encoding=encoding_dict,
                    unlimited_dims="time",
                )
                print(f"....Finished {v} IC processing!")
    return output_paths

if __name__ == "__main__":
    print(
        "This script is used to format the dataset to MOM6 formats, including applying necessary transformations & fills"
    )