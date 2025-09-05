import format_dataset as fd
import parse_dataset as pd
import regrid_dataset as rd
import subset_dataset as sd
import xarray as xr
from pathlib import Path
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info
from CrocoDash.grid import Grid
import sys
import json 

def test_driver():
    print("All Imports Work!")
    return


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

    # Get the variable_names from the setup
    variable_names = []
    variable_names.append(params["cesm_information"]["u"])
    variable_names.append(params["cesm_information"]["v"])
    variable_names.append(params["cesm_information"]["eta"])
    for key in params["cesm_information"]["tracers"]:
        variable_names.append(params["cesm_information"]["tracers"][key])


    # Parse the raw dataset
    if parse_dataset:
        variable_info = pd.parse_dataset(
            variable_names,
            Path(params["paths"]["input_path"]),
            params["dates"]["start"],
            params["dates"]["end"],
            params["cesm_information"]["space_character"],

        )

    # Subset the dataset based on geographical bounds
    if subset_dataset:
        grid = Grid.from_supergrid(params["paths"]["supergrid_path"])
        boundary_info = get_rectangular_segment_info(grid)
        sd.subset_dataset(
            variable_info=variable_info,
            output_path=params["paths"]["subset_input_path"],
            lat_min=boundary_info["ic"]["lat_min"],
            lat_max=boundary_info["ic"]["lat_max"],
            lon_min=boundary_info["ic"]["lon_min"],
            lon_max=boundary_info["ic"]["lon_max"],
            lat_name=params["cesm_information"]["yh"],
            lon_name=params["cesm_information"]["xh"],
            preview=params["general"]["preview"],
        )

    # Regrid the dataset to the boundaries
    if regrid_dataset:
        supergrid = xr.open_dataset(params["paths"]["supergrid_path"])
        rd.regrid_dataset_to_boundaries(
            params["paths"]["subset_input_path"],
            params["paths"]["regrid_path"],
            supergrid,
            variable_info,
            params["cesm_information"]["yh"],
            params["cesm_information"]["xh"],
            params["general"]["preview"],
        )

    # Format the dataset to MOM6 formats
    if format_dataset:
        supergrid = xr.open_dataset(params["paths"]["supergrid_path"])
        bathymetry = xr.open_dataset(params["paths"]["bathymetry_path"])
        output_paths = fd.format_dataset(
            params["paths"]["regrid_path"],
            params["paths"]["output_path"],
            supergrid,
            bathymetry,
            variable_info,
            params["cesm_information"]["yh"],
            params["cesm_information"]["xh"],
            params["cesm_information"]["zl"],
            params["general"]["boundary_number_conversion"],
        )
        return output_paths


if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_driver()
    else:
        workflow_dir = Path(__file__).parent

        # Read in config
        config_path = workflow_dir / "config.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        extract_obcs(config)
