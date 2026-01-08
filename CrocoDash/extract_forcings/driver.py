import sys
import json
from pathlib import Path

parent_dir = Path(__file__).parent
sys.path.append(str(parent_dir / "code"))
import merge_piecewise_dataset as mpd
import get_dataset_piecewise as gdp
import regrid_dataset_piecewise as rdp


def test_driver():
    """Test that all the imports work"""
    print("All Imports Work!")
    # Test Config
    workflow_dir = Path(__file__).parent
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    print("Config Loads!")
    return


def main(
    get_dataset_piecewise=True,
    regrid_dataset_piecewise=True,
    merge_piecewise_dataset=True,
):
    """
    Driver file to run the large data workflow
    """
    workflow_dir = Path(__file__).parent

    # Read in config
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)

    # Call get_dataset_piecewise
    if get_dataset_piecewise:
        gdp.get_dataset_piecewise(
            product_name=config["basic"]["forcing"]["product_name"],
            function_name=config["basic"]["forcing"]["function_name"],
            product_information=config["basic"]["forcing"]["information"],
            date_format=config["basic"]["dates"]["format"],
            start_date=config["basic"]["dates"]["start"],
            end_date=config["basic"]["dates"]["end"],
            hgrid_path=config["basic"]["paths"]["hgrid_path"],
            step_days=int(config["basic"]["general"]["step"]),
            output_dir=config["basic"]["paths"]["raw_dataset_path"],
            boundary_number_conversion=config["basic"]["general"]["boundary_number_conversion"],
            run_initial_condition=config["basic"]["general"]["run_initial_condition"],
            run_boundary_conditions=config["basic"]["general"]["run_boundary_conditions"],
            preview=config["basic"]["general"]["preview"],
        )

    # Call regrid_dataset_piecewise
    if regrid_dataset_piecewise:
        rdp.regrid_dataset_piecewise(
            config["basic"]["paths"]["raw_dataset_path"],
            config["basic"]["file_regex"]["raw_dataset_pattern"],
            config["basic"]["dates"]["format"],
            config["basic"]["dates"]["start"],
            config["basic"]["dates"]["end"],
            config["basic"]["paths"]["hgrid_path"],
            config["basic"]["paths"]["bathymetry_path"],
            config["basic"]["forcing"]["information"],
            config["basic"]["paths"]["regridded_dataset_path"],
            config["basic"]["general"]["boundary_number_conversion"],
            config["basic"]["general"]["run_initial_condition"],
            config["basic"]["general"]["run_boundary_conditions"],
            config["basic"]["paths"]["vgrid_path"],
            config["basic"]["general"]["preview"],
        )

    # Call merge_dataset_piecewise
    if merge_piecewise_dataset:
        mpd.merge_piecewise_dataset(
            config["basic"]["paths"]["regridded_dataset_path"],
            config["basic"]["file_regex"]["regridded_dataset_pattern"],
            config["basic"]["dates"]["format"],
            config["basic"]["dates"]["start"],
            config["basic"]["dates"]["end"],
            config["basic"]["general"]["boundary_number_conversion"],
            config["basic"]["paths"]["output_path"],
            config["basic"]["general"]["run_initial_condition"],
            config["basic"]["general"]["run_boundary_conditions"],
            config["basic"]["general"]["preview"],
        )
    return


if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_driver()
    else:
        main()
