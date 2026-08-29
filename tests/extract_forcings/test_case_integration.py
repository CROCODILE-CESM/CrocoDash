import subprocess
import json


def test_case_integration_driver(CrocoDash_case_factory, tmp_path, skip_if_not_glade):
    """Verify configure_forcings creates extract_forcings/ and crocodash process can load it."""
    case = CrocoDash_case_factory(tmp_path)
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-02 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
    )
    large_data_workflow_path = case.inputdir / "extract_forcings"
    assert (large_data_workflow_path).exists()
    # No component flags → "No components selected", returncode 0
    result = subprocess.run(
        ["crocodash", "process", "--caseroot", str(case.caseroot)],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    assert result.returncode == 0
    assert "--all" in result.stdout


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
    assert set(config["conditions"].keys()) == {"name", "inputs", "outputs"}
    assert "caseroot" in config
    # freq is the one overridable arg on GLORYS's default download function:
    # every dated access method takes it, and it is deliberately not in
    # required_args so it surfaces here as a tunable that function_overrides
    # will accept. None means "the product's native cadence".
    assert config["conditions"]["outputs"]["function_args"] == {"freq": None}


def test_case_integration_freq_override(CrocoDash_case_factory, tmp_path):
    """A coarser freq must be accepted by configure_forcings and recorded.

    This is the user-facing half of the frequency contract: function_overrides
    is validated against the access method's own overridable args, so freq
    reaching config.json here is what lets a year of daily GLORYS be fetched as
    13 monthly stamps instead of 369 daily ones.
    """
    case = CrocoDash_case_factory(tmp_path)
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
        product_name="GLORYS",
        function_name="get_glorys_data_from_rda",
        function_overrides={"freq": "MS"},
    )
    with open(case.inputdir / "extract_forcings" / "config.json") as f:
        config = json.load(f)
    assert config["conditions"]["outputs"]["function_args"]["freq"] == "MS"


def test_case_integration_rejects_finer_than_native_freq(
    CrocoDash_case_factory, tmp_path
):
    """A freq finer than the product's cadence must fail, not silently under-fetch."""
    import pytest

    case = CrocoDash_case_factory(tmp_path)
    with pytest.raises(ValueError, match="finer than"):
        case.configure_forcings(
            date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
            boundaries=["north", "south", "east"],
            too_much_data=True,
            product_name="GLORYS",
            function_name="get_glorys_data_from_rda",
            function_overrides={"freq": "6h"},
        )


def test_driver_works(CrocoDash_case_factory, tmp_path):
    """Verify configure_forcings creates the right structure and crocodash process can be invoked."""
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
        ["crocodash", "process", "--caseroot", str(case.caseroot), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--all" in result.stdout
