import subprocess
import json


def test_case_integration_driver(CrocoDash_case_factory, tmp_path, skip_if_not_glade):
    case = CrocoDash_case_factory(tmp_path)
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-02 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
    )
    large_data_workflow_path = case.inputdir / "extract_forcings"
    assert (large_data_workflow_path).exists()
    result = subprocess.run(
        ["python", large_data_workflow_path / "driver.py", "test"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)  # Output of the script
    assert result.returncode == 0

    return


def test_case_integration_config(CrocoDash_case_factory, tmp_path):
    case = CrocoDash_case_factory(tmp_path)
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
        product_name="GLORYS",
        function_name="get_glorys_data_script_for_cli",
    )
    large_data_workflow_path = case.inputdir / "extract_forcings"
    assert (large_data_workflow_path).exists()
    with open(large_data_workflow_path / "config.json", "r") as f:
        config = json.load(f)
    # Top-level keys
    assert set(config["basic"].keys()) == {
        "paths",
        "file_regex",
        "dates",
        "forcing",
        "general",
    }


def test_driver_works(CrocoDash_case_factory, tmp_path):
    """
    Test that the setup for the forcings works
    """
    case = CrocoDash_case_factory(tmp_path / "case")
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath=tmp_path,
        tpxo_velocity_filepath=tmp_path,
        chl_processed_filepath=tmp_path,
        boundaries=["north", "south", "east"],
    )
    large_data_workflow_path = case.inputdir / "extract_forcings"
    assert (large_data_workflow_path).exists()
    result = subprocess.run(
        ["python", large_data_workflow_path / "driver.py", "--tides"],
        capture_output=True,
        text=True,
    )
