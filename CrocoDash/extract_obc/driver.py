import format_dataset as fd
import parse_dataset as pd
import regrid_dataset as rd
import subset_dataset as sd
from pathlib import Path
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info
from CrocoDash.grid import Grid


def extract_obcs(
    params: dict,
    parse_dataset=True,
    subset_dataset=True,
    regrid_dataset=True,
    format_dataset=True,
) -> dict:
    """
    Extract Open Boundary Conditions (OBCs) from a dataset.

    Args:
        params (dict): Parameters for the extraction process.
    Returns:
        dict: Paths to the output files for each boundary.
    """

    # Parse the raw dataset
    if parse_dataset:
        variable_info = pd.parse_dataset(params["variable_names"], Path(input_path))

    # Subset the dataset based on geographical bounds
    if subset_dataset:
        grid = Grid.from_supergrid(params["supergrid_path"])
        boundary_info = get_rectangular_segment_info(grid)
        sd.subset_dataset(
            variable_info=variable_info,
            output_path=params["subset_input_path"],
            lat_min=boundary_info["ic"]["lat_min"],
            lat_max=boundary_info["ic"]["lat_max"],
            lon_min=boundary_info["ic"]["lon_min"],
            lon_max=boundary_info["ic"]["lon_max"],
            lat_name=params["lat_name"],
            lon_name=params["lon_name"],
            preview=params["preview"],
        )

    # Regrid the dataset to the boundaries
    if regrid_dataset:
        supergrid = xr.open_dataset(params["supergrid_path"])
        rd.regrid_dataset_to_boundaries(
            params["subset_input_path"],
            params["regrid_path"],
            supergrid,
            variable_info,
            params["lat_name"],
            params["lon_name"],
            params["preview"],
        )

    # Format the dataset to MOM6 formats
    if format_dataset:
        supergrid = xr.open_dataset(params["supergrid_path"])
        bathymetry = xr.open_dataset(params["bathymetry_path"])
        output_paths = fd.format_dataset(
            params["regrid_path"],
            params["output_path"],
            supergrid,
            bathymetry,
            variable_info,
            params["lat_name"],
            params["lon_name"],
            params["z_dim"],
        )
        return output_paths
