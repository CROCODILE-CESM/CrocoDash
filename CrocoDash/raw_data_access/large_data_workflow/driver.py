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


def main():
    """
    Driver file to run the large data workflow
    """
    workflow_dir = Path(__file__).parent

    # Read in config
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)

    # Call get_dataset_piecewise
    gdp.get_dataset_piecewise(
        product_name=config["forcing"]["product_name"],
        function_name=config["forcing"]["function_name"],
        date_format=config["dates"]["format"],
        start_date=config["dates"]["start"],
        end_date=config["dates"]["end"],
        hgrid_path=config["paths"]["hgrid_path"],
        step_days=int(config["params"]["step"]),
        output_dir=config["paths"]["raw_dataset_path"],
        boundary_number_conversion=config["boundary_number_conversion"],
        preview=config["params"]["preview"],
    )

    # Call regrid_dataset_piecewise
    rdp.regrid_dataset_piecewise(
        config["paths"]["regridded_dataset_path"],
        config["file_regex"]["raw_dataset_pattern"],
        config["dates"]["format"],
        config["dates"]["start"],
        config["dates"]["end"],
        config["paths"]["hgrid_path"],
        config["forcing"]["varnames"],
        config["paths"]["regridded_dataset_path"],
        config["boundary_number_conversion"],
        config["params"]["preview"],
    )

    # Call merge_dataset_piecewise
    mpd.merge_piecewise_dataset(
        config["paths"]["raw_dataset_path"],
        config["file_regex"]["regridded_dataset_pattern"],
        config["dates"]["format"],
        config["dates"]["start"],
        config["dates"]["end"],
        config["boundary_number_conversion"],
        config["paths"]["merged_dataset_path"],
        config["params"]["preview"],
    )
    return


if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_driver()
    else:
        main()
