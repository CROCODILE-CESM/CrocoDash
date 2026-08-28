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
    # GLORYS's default download function has no non-required args to override
    assert config["conditions"]["outputs"]["function_args"] == {}


def test_case_integration_config_cice_round_trip(CrocoDash_case_factory, tmp_path):
    """Verify cice_product_name/cice_function_name/cice_function_args round-trip
    through config.json into the exact keys CICEConfigurator.process reads
    (forcing/cice.py)."""
    case = CrocoDash_case_factory(
        tmp_path, compset="2000_DATM%JRA_SLND_CICE%PRES_MOM6_SROF_SGLC_SWAV"
    )
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-02 00:00:00"],
        boundaries=["north", "south"],
        cice_product_name="reference_ice",
        cice_function_name="get_reference_ice_data",
    )
    with open(case.inputdir / "extract_forcings" / "config.json", "r") as f:
        config = json.load(f)

    cice_inputs = config["cice"]["inputs"]
    assert cice_inputs["cice_product_name"] == "reference_ice"
    assert cice_inputs["cice_function_name"] == "get_reference_ice_data"
    assert cice_inputs["cice_function_args"] == {}
    assert cice_inputs["n_halo_cells"] == 2


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
