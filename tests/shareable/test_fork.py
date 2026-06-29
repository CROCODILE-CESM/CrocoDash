from CrocoDash.shareable.fork import *
import json
import pytest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4


@pytest.fixture
def fake_fcb_empty_case():
    fcb = ForkCrocoDashBundle.__new__(ForkCrocoDashBundle)
    return fcb


@pytest.fixture(scope="session")
def sample_forcing_config():
    forcing_config = {
        "basic": {
            "dates": {
                "start": "20200101",
                "end": "20200109",
                "format": "%Y%m%d",
            },
            "forcing": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_script_for_cli",
            },
            "general": {"boundary_number_conversion": {"north": 1}},
        },
        "tides": {
            "inputs": {
                "tidal_constituents": ["M2", "K1"],
                "boundaries": ["north"],
                "tpxo_elevation_filepath": "ASd",
                "tpxo_velocity_filepath": "ASd",
                "case_specific_param": "asdsd",
            }
        },
        "bgcic": {
            "inputs": {
                "marbl_ic_filepath": "qwreqwre",
            }
        },
    }
    return forcing_config


def test_resolve_copy_plan_all_missing(fake_fcb_empty_case):
    """Test _resolve_copy_plan sets correct plan when all differences exist."""
    fcb = fake_fcb_empty_case
    fcb.differences = BundleDifferences(
        xml_files_missing_in_new=["custom.xml"],
        user_nl_missing_params={"user_nl_mom": ["PARAM1"]},
        source_mods_missing_files=["src.mom/file.F90"],
        xmlchanges_missing=["JOB_PRIORITY"],
    )

    with patch("CrocoDash.shareable.fork.ask_yes_no", return_value=True):
        fcb._resolve_copy_plan(None)

    assert fcb.plan.get("xml_files") is True
    assert fcb.plan.get("user_nl") is True
    assert fcb.plan.get("source_mods") is True
    assert fcb.plan.get("xmlchanges") is True


def test_resolve_copy_plan_no_differences(fake_fcb_empty_case):
    """Test _resolve_copy_plan sets empty plan when no differences."""
    fcb = fake_fcb_empty_case
    fcb.differences = BundleDifferences()

    fcb._resolve_copy_plan(None)

    assert len(fcb.plan) == 0


def test_resolve_copy_plan_with_provided_plan(fake_fcb_empty_case):
    """Test _resolve_copy_plan uses provided plan without prompting."""
    fcb = fake_fcb_empty_case
    provided = {"xml_files": False, "user_nl": True}

    fcb._resolve_copy_plan(provided)

    assert fcb.plan is provided


def test_resolve_compset(fake_fcb_empty_case):
    """Test _resolve_compset sets compset on self."""
    fcb = fake_fcb_empty_case
    bundle_compset = "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    fcb.manifest = BundleManifest(
        forcing_config={},
        init_args={"compset": bundle_compset},
    )

    fcb._resolve_compset(None)

    assert fcb.compset == bundle_compset

    new_compset = "2000_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    fcb._resolve_compset(new_compset)

    assert fcb.compset == new_compset


def test_build_general_configure_forcing_args(sample_forcing_config):
    """Test generate_configure_forcing_args creates correct argument dict."""
    forcing_config = sample_forcing_config

    remove_configs = set()

    args = generate_configure_forcing_args(forcing_config, remove_configs)

    assert args["date_range"] == ["2020-01-01 00:00:00", "2020-01-09 00:00:00"]
    assert args["boundaries"] == ["north"]
    assert args["product_name"] == "GLORYS"
    assert args["function_name"] == "get_glorys_data_script_for_cli"
    assert args["tidal_constituents"] == ["M2", "K1"]
    assert "case_specific_param" not in args

    remove_configs = {"tides"}

    args = generate_configure_forcing_args(forcing_config, remove_configs)

    assert "tidal_constituents" not in args
    assert "marbl_ic_filepath" in args


def test_resolve_forcing_args_no_configs(fake_fcb_empty_case, sample_forcing_config):
    """Test _resolve_forcing_args sets configure_forcing_args unchanged when no configs requested."""
    fcb = fake_fcb_empty_case
    fcb.manifest = BundleManifest(forcing_config=sample_forcing_config, init_args={})
    fcb.resolved_remove = {}
    fcb.requested_configs = []

    fcb._resolve_forcing_args(None)

    assert fcb.configure_forcing_args == {
        "date_range": ["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        "boundaries": ["north"],
        "product_name": "GLORYS",
        "function_name": "get_glorys_data_script_for_cli",
        "tpxo_elevation_filepath": "ASd",
        "tpxo_velocity_filepath": "ASd",
        "tidal_constituents": ["M2", "K1"],
        "marbl_ic_filepath": "qwreqwre",
    }


def test_resolve_forcing_args_with_json_file(
    fake_fcb_empty_case, sample_forcing_config, tmp_path
):
    """Test that _resolve_forcing_args loads extra args from a JSON file path."""
    fcb = fake_fcb_empty_case
    fcb.manifest = BundleManifest(forcing_config=sample_forcing_config, init_args={})
    fcb.resolved_remove = {}
    fcb.requested_configs = ["tides"]

    args_file = tmp_path / "forcing_args.json"
    args_file.write_text(
        json.dumps(
            {
                "tidal_constituents": ["M2", "K1"],
                "tpxo_elevation_filepath": "elev.nc",
                "tpxo_velocity_filepath": "vel.nc",
                "boundaries": ["north"],
            }
        )
    )

    fcb._resolve_forcing_args(str(args_file))

    assert fcb.configure_forcing_args["tidal_constituents"] == ["M2", "K1"]


def test_resolve_forcing_args_missing_required_arg(
    fake_fcb_empty_case, sample_forcing_config, tmp_path
):
    """Test that _resolve_forcing_args raises ValueError when required args are missing."""
    fcb = fake_fcb_empty_case
    fcb.manifest = BundleManifest(forcing_config=sample_forcing_config, init_args={})
    fcb.resolved_remove = {"tides"}  # remove tides so its args aren't pre-populated
    fcb.requested_configs = ["tides"]

    args_file = tmp_path / "incomplete_args.json"
    args_file.write_text(json.dumps({"tidal_constituents": ["M2"]}))

    with pytest.raises(ValueError, match="Missing arg"):
        fcb._resolve_forcing_args(str(args_file))


def test_resolve_forcing_configurations(fake_fcb_empty_case, sample_forcing_config):
    """Test _resolve_forcing_configurations sets requested and removed configs on self."""
    fcb = fake_fcb_empty_case
    fcb.manifest = BundleManifest(forcing_config=sample_forcing_config, init_args={})
    fcb.compset = "2000_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"

    with patch(
        "CrocoDash.shareable.fork.ForcingConfigRegistry.find_required_configurators",
        return_value=[],
    ):
        with patch(
            "CrocoDash.shareable.fork.ForcingConfigRegistry.find_valid_configurators",
            return_value=[],
        ):
            with patch("CrocoDash.shareable.fork.ask_string", side_effect=["", "bgc"]):
                fcb._resolve_forcing_configurations(None, None)

    assert isinstance(fcb.requested_configs, list)
    assert isinstance(fcb.resolved_remove, set)
    assert "bgc" in fcb.resolved_remove


def test_resolve_forcing_configurations_required_missing(
    fake_fcb_empty_case, sample_forcing_config
):
    """Test that a required configurator absent from the manifest is added to requested_configs."""
    fcb = fake_fcb_empty_case
    # manifest has no "bgc" entry
    fcb.manifest = BundleManifest(forcing_config={"basic": {}}, init_args={})
    fcb.compset = "2000_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"

    mock_required = SimpleNamespace(name="BGC")

    with patch(
        "CrocoDash.shareable.fork.ForcingConfigRegistry.find_required_configurators",
        return_value=[mock_required],
    ), patch(
        "CrocoDash.shareable.fork.ForcingConfigRegistry.find_valid_configurators",
        return_value=[],
    ):
        fcb._resolve_forcing_configurations(extra_configs=[], remove_configs=[])

    assert "bgc" in fcb.requested_configs


def test_ask_input_response():
    """Test ask_yes_no returns True for yes/y response."""
    with patch("builtins.input", return_value="yes"):
        result = ask_yes_no("Continue?")

    with patch("builtins.input", return_value="no"):
        result = ask_yes_no("Continue?")

    assert result is False

    with patch("builtins.input", return_value="test input"):
        result = ask_string("Enter something: ")

    assert result == "test input"


def test_create_case(get_CrocoDash_case, tmp_path):
    """Test create_case properly constructs a Case object from bundle data."""
    original_case = get_CrocoDash_case

    init_args = {
        "inputdir_ocnice": original_case.inputdir,
        "supergrid_path": original_case.supergrid_path,
        "topo_path": original_case.topo_path,
        "vgrid_path": original_case.vgrid_path,
        "compset": original_case.compset_lname,
        "atm_grid_name": "TL319",
    }

    new_caseroot = tmp_path / f"new_case-{uuid4().hex}"
    new_inputdir = tmp_path / f"new_inputdir-{uuid4().hex}"
    new_inputdir.mkdir()

    case = create_case(
        init_args,
        new_caseroot,
        new_inputdir,
        machine=original_case.machine,
        project_number=original_case.project,
        cesmroot=original_case.cime.cimeroot.parent,
        compset=original_case.compset_lname,
    )

    assert case.caseroot == new_caseroot
    assert case.inputdir == new_inputdir
    assert case.ocn_grid is not None
    assert case.ocn_topo is not None
    assert case.ocn_vgrid is not None
    assert case.machine == original_case.machine
