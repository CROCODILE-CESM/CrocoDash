"""
Regrid the datasets to a specified grid using regional_mom6 tools and xesmf
"""

from regional_mom6 import regridding as rgd
import xarray as xr
import json
from pathlib import Path

REGRID_ITEMS = ["IC", "west", "south", "north", "east"]


def regrid_dataset_to_boundaries(
    input_path: str | Path,
    output_path: str | Path,
    supergrid: xr.Dataset,
    variable_info: dict,
    u_name: str = None,
    v_name: str = None,
    lat_name: str = "lat",
    lon_name: str = "lon",
    u_lat_name: str = "lat",
    u_lon_name: str = "lon",
    v_lat_name: str = "lat",
    v_lon_name: str = "lon",
    boundaries: list[str] = ["south", "north", "west", "east"],
    preview=False,
):
    """
    Regrid the datasets to specified boundaries using regional_mom6 tools.

    Args:
        input_path (str | Path): Path to the input dataset.
        output_path (str | Path): Path to save the regridded dataset.
        supergrid (xr.Dataset): The supergrid dataset to regrid onto.
        variable_info (dict): Dictionary containing variable names and their file paths.
        boundaries (list[str]): List of boundaries
    """

    # Make sure the paths is a Path object and exists
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    if not input_path.exists():
        raise ValueError(f"Input path {input_path} does not exist.")

    # Calculate the correct lon/lat units
    ds = xr.open_dataset(input_path / f"{u_name}_subset.nc", decode_times=False)
    dataset_is_degrees_east_longitude = False
    if ds[u_lon_name].max()>180:
        dataset_is_degrees_east_longitude = True
    
    if dataset_is_degrees_east_longitude:
        supergrid["x"] = supergrid.x % 360
        
    else:
        supergrid["x"] = ((supergrid.x + 180) % 360) - 180

    regridders = create_regridders(
        input_path,
        output_path,
        supergrid,
        variable_info,
        u_name,
        v_name,
        lat_name,
        lon_name,
        u_lat_name,
        u_lon_name,
        v_lat_name,
        v_lon_name,
    )

    output_paths = []

    # Regrid and save the datasets
    for item in REGRID_ITEMS:
        if item not in boundaries and item != "IC":
            continue
        for v in variable_info:
            try:
                print(f"Regridding {v} {item}")
                input_file = input_path / f"{v}_subset.nc"
                output_file = output_path / f"{v}_{item}_regridded.nc"
                if output_file.exists():
                    print(f"{output_file} already exists, skipping.")
                    output_paths.append(str(output_file.resolve()))
                    continue
                with xr.open_dataset(
                    input_file, decode_times=False, chunks="auto"
                ) as ds:
                    ds = ds.rename({lon_name: "lon", lat_name: "lat"})

                    # Perform regridding
                    if not preview:
                        if v in (u_name, v_name) and item == "IC":
                            regridded = regridders[item + v](ds[v])
                        else:
                            regridded = regridders[item](ds[v])

                        # Save regridded dataset
                        regridded.to_netcdf(output_file)
                        regridded.close()
                    output_paths.append(str(output_file.resolve()))

                print(f"{v} {item} regridded")

            except Exception as e:
                print(f"Failed to regrid {v} {item}: {e}")

    return output_paths


def create_regridders(
    input_path: str | Path,
    output_path: str | Path,
    supergrid: xr.Dataset,
    variable_info: dict,
    u_name: str,
    v_name: str,
    lat_name: str = "lat",
    lon_name: str = "lon",
    u_lat_name: str = "lat",
    u_lon_name: str = "lon",
    v_lat_name: str = "lat",
    v_lon_name: str = "lon",
) -> dict:
    """
    Return Regridders for each boundary using regional_mom6 tools.
    """
    hgrid = supergrid
    tgrid = (
        rgd.get_hgrid_arakawa_c_points(hgrid, "t")
        .rename({"tlon": "lon", "tlat": "lat", "nxp": "nx", "nyp": "ny"})
        .set_coords(["lat", "lon"])
    )
    vgrid = (
        rgd.get_hgrid_arakawa_c_points(hgrid, "v")
        .rename({"vlon": "lon", "vlat": "lat", "nxp": "nx"})
        .set_coords(["lat", "lon"])
    )
    ugrid = (
        rgd.get_hgrid_arakawa_c_points(hgrid, "u")
        .rename({"ulon": "lon", "ulat": "lat", "nyp": "ny"})
        .set_coords(["lat", "lon"])
    )
    # Create regridders for each boundary
    variable_to_use = next(iter(variable_info.keys()))
    regridders = {}
    ds = xr.open_dataset(
        input_path / f"{variable_to_use}_subset.nc", decode_times=False
    )
    ds["lon"] = ds[lon_name]
    ds["lat"] = ds[lat_name]
    if u_name != None:
        ds_u = xr.open_dataset(input_path / f"{u_name}_subset.nc", decode_times=False)
        ds_u["lon"] = ds_u[lon_name]
        ds_u["lat"] = ds_u[lat_name]
        regridders["IC" + u_name] = rgd.create_regridder(
            ds_u[["lon", "lat", u_name]],
            ugrid,
            locstream_out=False,
            outfile=output_path / f"{'IC'+u_name}_weights.nc",
        )
    if v_name != None:
        ds_v = xr.open_dataset(input_path / f"{v_name}_subset.nc", decode_times=False)
        ds_v["lon"] = ds_v[lon_name]
        ds_v["lat"] = ds_v[lat_name]

        # Create Velocity Regridders

        regridders["IC" + v_name] = rgd.create_regridder(
            ds_v[["lon", "lat", v_name]],
            vgrid,
            locstream_out=False,
            outfile=output_path / f"{'IC'+v_name}_weights.nc",
        )
    for item in REGRID_ITEMS:
        print(f"Creating regridder for {item}")
        if item == "IC":
            # Initial Condition must be handled seperately in 2D

            regridders[item] = rgd.create_regridder(
                ds[["lon", "lat", variable_to_use]],
                tgrid,
                locstream_out=False,
                outfile=output_path / f"{item}_weights.nc",
            )
        else:
            coords = rgd.coords(hgrid, item, "segment_{}".format(item))
            regridders[item] = rgd.create_regridder(
                ds[["lon", "lat", variable_to_use]],
                coords,
                locstream_out=True,
                outfile=output_path / f"{item}_weights.nc",
            )
    return regridders


if __name__ == "__main__":
    print(
        "This script is used to regrid the datasets to a specified grid using regional_mom6 tools and xesmf."
    )
