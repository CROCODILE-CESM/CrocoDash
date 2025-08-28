import subprocess
import json


def test_case_integration_driver(get_CrocoDash_case, skip_if_not_glade):
    case = get_CrocoDash_case
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-02 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
    )
    large_data_workflow_path = (
        case.inputdir / case.forcing_product_name / "large_data_workflow"
    )
    assert (large_data_workflow_path).exists()
    result = subprocess.run(
        ["python", large_data_workflow_path / "driver.py", "test"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)  # Output of the script
    assert result.returncode == 0

    return


def test_case_integration_config(get_CrocoDash_case):
    case = get_CrocoDash_case
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
        product_name="GLORYS",
        function_name="get_glorys_data_script_for_cli",
    )
    large_data_workflow_path = (
        case.inputdir / case.forcing_product_name / "large_data_workflow"
    )
    assert (large_data_workflow_path).exists()
    with open(large_data_workflow_path / "config.json", "r") as f:
        config = json.load(f)
    # Top-level keys
    assert set(config.keys()) == {
        "paths",
        "file_regex",
        "dates",
        "forcing",
        "boundary_number_conversion",
        "params",
    }

    # Paths
    assert isinstance(config["paths"], dict)
    assert set(config["paths"].keys()) == {
        "raw_dataset_path",
        "hgrid_path",
        "vgrid_path",
        "regridded_dataset_path",
        "merged_dataset_path",
    }
    assert all(isinstance(val, str) for val in config["paths"].values())

    # Raw file regex
    assert isinstance(config["file_regex"], dict)
    assert set(config["file_regex"].keys()) == {
        "raw_dataset_pattern",
        "regridded_dataset_pattern",
    }
    assert all(isinstance(val, str) for val in config["file_regex"].values())

    # Dates
    assert isinstance(config["dates"], dict)
    assert set(config["dates"].keys()) == {"start", "end", "format"}
    assert all(isinstance(val, str) for val in config["dates"].values())

    # Forcing
    assert isinstance(config["forcing"], dict)
    assert set(config["forcing"].keys()) == {
        "product_name",
        "function_name",
        "varnames",
    }
    assert isinstance(config["forcing"]["product_name"], str)
    assert isinstance(config["forcing"]["function_name"], str)
    assert isinstance(config["forcing"]["varnames"], dict)

    # Boundary number conversion
    assert isinstance(config["boundary_number_conversion"], dict)

    # Params
    assert isinstance(config["params"], dict)
    assert set(config["params"].keys()) == {"step", "preview", "run_initial_condition","run_boundary_conditions"}
    assert isinstance(config["params"]["step"], int)
    assert isinstance(config["params"]["preview"], bool)
    assert isinstance(config["params"]["run_initial_condition"], bool)

    # Validate every param except ocean_hgrid, boundary_number_conversion, and ocean_varnames
    assert config["paths"]["raw_dataset_path"] == str(
        large_data_workflow_path / "raw_data"
    )
    assert config["paths"]["regridded_dataset_path"] == str(
        large_data_workflow_path / "regridded_data"
    )
    assert config["paths"]["merged_dataset_path"] == str(case.inputdir / "ocnice")

    # Raw file regex
    assert (
        config["file_regex"]["raw_dataset_pattern"]
        == "(north|east|south|west)_unprocessed\\.(\\d{8})_(\\d{8})\\.nc"
    )
    assert (
        config["file_regex"]["regridded_dataset_pattern"]
        == "forcing_obc_segment_(\\d{3})_(\\d{8})_(\\d{8})\\.nc"
    )

    # Dates
    assert config["dates"]["start"] == "20200101"
    assert config["dates"]["end"] == "20200201"
    assert config["dates"]["format"] == "%Y%m%d"

    # Forcing
    assert config["forcing"]["product_name"] == "GLORYS"
    assert config["forcing"]["function_name"] == "get_glorys_data_script_for_cli"

    # Params
    assert config["params"]["step"] == 5
    assert config["params"]["preview"] == False
    assert config["params"]["run_initial_condition"] == True
    return
