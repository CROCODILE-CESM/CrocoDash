"""
This script is used to load the regridded datasets on a regional supergrid and format them into the required structure for MOM6
"""

from regional_mom6 import regridding as rgd
import xarray as xr
import json
from pathlib import Path
import numpy as np
from mom6_bathy.vgrid import *
REGRID_ITEMS = ["IC", "west", "south", "north", "east"]


def format_dataset(
    input_path: str | Path,
    output_path: str | Path,
    supergrid: xr.Dataset,
    bathymetry: xr.Dataset,
    vgrid: xr.Dataset,
    variable_info: dict,
    u_name: str,
    v_name: str,
    lat_name: str = "lat",
    lon_name: str = "lon",
    z_dim: str = "z_t",
    z_unit_conversion: float = "1",
    boundary_number_conversion: dict = {"south": 1, "north": 2, "west": 3, "east": 4},
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
        z_dim (str): Name of the vertical dimension in the dataset. Default is "z_t".
        boundary_number_conversion (dict): Mapping of boundary names to segment numbers.

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
        for item in REGRID_ITEMS:
            # Open Dataset
            ds = xr.open_dataset(input_path / f"{v}_{item}_regridded.nc")

            # Ensure the correct z_dim if it is a list of potential z_dims
            if type(z_dim) is list:
                    found_z_dim = False
                    for z_dim_opt in z_dim:
                        if z_dim_opt in ds["__xarray_dataarray_variable__"].dims:
                            z_dim_act = z_dim_opt
                            found_z_dim = True
                            break
                    if not found_z_dim:
                        print(f"Did not find any of the provided z_dims in the dataset for {v} {item}, assuming surface variable")
                        z_dim_act = None

            # Do unit conversion for distance units
            if z_dim_act != None:
                
                ds[z_dim_act] = ds[z_dim_act] * z_unit_conversion
            if v == u_name or v == v_name or z_dim_act == None: # A check if this is a velocity/surface height variable (only one with no z dim)
                print(f"Converting the {v} variable because it is distance based with factor {z_unit_conversion}")
                ds["__xarray_dataarray_variable__"] = ds["__xarray_dataarray_variable__"] * z_unit_conversion

                
            # Convert the z dimension variable with the unit conversion factor if provided
            if item != "IC":
                segment_name = "segment_{:03d}".format(boundary_number_conversion[item])
                file_path = output_path / f"{v}_obc_{segment_name}.nc"
                if file_path.exists():
                    print(f"Already processed {v} {item}, skipping!")
                    continue

                ## Apply Unit Conversion if needed

                ## Continue formatting
                # Rename improtant dim to number convention
                dim_name = ds.variables["__xarray_dataarray_variable__"].dims[-1]
                parts = dim_name.split("_")
                parts[-1] = f"{boundary_number_conversion[parts[-1]]:03d}"
                new_dim_name = "_".join(parts)
                ds = ds.rename({dim_name: new_dim_name})
                dim_name = new_dim_name

                coords = rgd.coords(supergrid, item, segment_name)
                ds[v] = ds.__xarray_dataarray_variable__
                ds = ds.drop_vars(["__xarray_dataarray_variable__"])
                ds = ds.rename(
                    {"lon": f"lon_{segment_name}", "lat": f"lat_{segment_name}"}
                )
                item_name = f"{v}_{segment_name}"
                ds = ds.rename({v: item_name})

                
                ds[item_name] = rgd.fill_missing_data(
                    ds[item_name],
                    xdim=dim_name,
                    zdim=z_dim_act,
                )

                if z_dim_act not in ds[item_name].dims:
                    print(
                        "This variable is only a surface variable, skipping z_dim_act conversion."
                    )
                    z_dim_act = None
                    ds = rgd.add_secondary_dimension(
                        ds, item_name, coords, segment_name
                    )
                else:
                    ds = rgd.vertical_coordinate_encoding(
                        ds, item_name, segment_name, z_dim_act
                    )
                    ds = rgd.add_secondary_dimension(
                        ds, item_name, coords, segment_name
                    )
                    ds = rgd.generate_layer_thickness(
                        ds, item_name, segment_name, z_dim_act
                    )

                # Overwrite actual lat/lon vals with grid numbers in these variables
                ds[f"{coords.attrs['parallel']}_{segment_name}"] = np.arange(
                    ds[f"{coords.attrs['parallel']}_{segment_name}"].size
                )
                ds[f"{coords.attrs['perpendicular']}_{segment_name}"] = [0]

                ds = rgd.mask_dataset(
                    ds,
                    bathymetry,
                    item,
                )
                # Add Time units
                ds.time.attrs = {
                    "calendar": "julian",
                    "units": f"days since 1850-01-01 00:00:00",
                }
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
                print(f"....Finished {v} {item} processing!")
            else:
                file_path = output_path / f"{v}_IC.nc"
                if file_path.exists():
                    print(f"Already processed {v} Initial Condition, skipping!")
                    continue
                # Slice the velocites to the u and v grid.
                u_points = rgd.get_hgrid_arakawa_c_points(supergrid, "u")
                v_points = rgd.get_hgrid_arakawa_c_points(supergrid, "v")
                t_points = rgd.get_hgrid_arakawa_c_points(supergrid, "t")

                ds[v] = ds.__xarray_dataarray_variable__

                # Drop old var
                ds = ds.drop_vars(["__xarray_dataarray_variable__"])

                # Fill Missing Data
                if z_dim_act not in ds[v].dims:
                    z_dim_act = None
                if "nxp" in ds[v].dims:
                    x_dim = "nxp"
                else:
                    x_dim = "nx"
                if "nyp" in  ds[v].dims:
                    y_dim = "nyp"
                else:
                    y_dim = "ny"
                ds[v] = rgd.fill_missing_data(
                    ds[v],
                    xdim=x_dim,
                    zdim=z_dim_act,
                )

                ds[v] = ds[v].isel(time=0, drop=True)
                

                ds[x_dim] = ds[x_dim]
                ds[y_dim] = ds[y_dim]

                # Interpolate the vertical levels
                if z_dim_act != None:
                    zl = np.cumsum(vgrid.dz) - 0.5 * vgrid.dz
                    ds = ds.interp({z_dim_act:zl.values},
                        kwargs={"fill_value": "extrapolate"})

                # Do Encoding
                encoding_dict = {
                    "time": {"dtype": "double", "_FillValue": 1.0e2},
                    v:{  "_FillValue": 1.0e2}
                }

                # Save File Out
                output_paths.append(file_path)
                ds.load().to_netcdf(
                    file_path,
                    encoding=encoding_dict,
                    unlimited_dims="time",
                )
                print(f"....Finished {v} IC processing!")

    # Merge U & V Files
    file_path = output_path / f"VEL_IC.nc"
    if not file_path.exists():
        print("Merging U & V velocity files")
        vvel = xr.open_dataset(output_path / f"{v_name}_IC.nc")
        uvel = xr.open_dataset(output_path / f"{u_name}_IC.nc")
        vvel[u_name] = uvel[u_name]
        encoding_dict = {
                    "time": {"dtype": "double", "_FillValue": 1.0e2},
                }

        encoding_dict = rgd.generate_encoding(
            vvel,
            encoding_dict,
            default_fill_value=1.0e2,
        )
        vvel.load().to_netcdf(
                    file_path,
                    encoding=encoding_dict,
                    unlimited_dims="time",
                )
        
    return output_paths


if __name__ == "__main__":
    print(
        "This script is used to format the dataset to MOM6 formats, including applying necessary transformations & fills"
    )
