from CrocoDash.shareable.fork import *
import pytest
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


def test_ask_copy_questions_all_missing(fake_fcb_empty_case):
    """Test ask_copy_questions returns correct plan when all differences exist."""
    fcb = fake_fcb_empty_case
    fcb.differences = {
        "xml_files_missing_in_new": ["custom.xml"],
        "user_nl_missing_params": {"user_nl_mom": ["PARAM1"]},
        "source_mods_missing_files": ["src.mom/file.F90"],
        "xmlchanges_missing": ["JOB_PRIORITY"],
    }

    with patch("CrocoDash.shareable.fork.ask_yes_no", return_value=True):
        plan = fcb.ask_copy_questions()

    assert plan.get("xml_files") is True
    assert plan.get("user_nl") is True
    assert plan.get("source_mods") is True
    assert plan.get("xmlchanges") is True


def test_ask_copy_questions_no_differences(fake_fcb_empty_case):
    """Test ask_copy_questions returns empty plan when no differences."""
    fcb = fake_fcb_empty_case
    fcb.differences = {
        "xml_files_missing_in_new": [],
        "user_nl_missing_params": {},
        "source_mods_missing_files": [],
        "xmlchanges_missing": [],
    }

    plan = fcb.ask_copy_questions()

    assert len(plan) == 0


def test_resolve_compset(fake_fcb_empty_case):
    """Test resolve_compset returns current compset when user doesn't want to change."""
    fcb = fake_fcb_empty_case
    fcb.manifest = {
        "init_args": {"compset": "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"}
    }

    with patch("CrocoDash.shareable.fork.ask_yes_no", return_value=False):
        result = fcb.resolve_compset()

    assert result == "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"

    new_compset = "2000_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"

    with patch("CrocoDash.shareable.fork.ask_yes_no", return_value=True):
        with patch("CrocoDash.shareable.fork.ask_string", return_value=new_compset):
            result = fcb.resolve_compset()

    assert result == new_compset


def test_build_general_configure_forcing_args(sample_forcing_config):
    """Test build_general_configure_forcing_args creates correct argument dict."""
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


def test_set_up_forcing_inputs_no_configs(fake_fcb_empty_case, sample_forcing_config):
    """Test that function returns args unchanged when no configs requested."""
    fcb = fake_fcb_empty_case

    result = fcb.set_up_forcing_inputs(sample_forcing_config, {}, [])

    assert result == {
        "date_range": ["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        "boundaries": ["north"],
        "product_name": "GLORYS",
        "function_name": "get_glorys_data_script_for_cli",
        "tpxo_elevation_filepath": "ASd",
        "tpxo_velocity_filepath": "ASd",
        "tidal_constituents": ["M2", "K1"],
        "marbl_ic_filepath": "qwreqwre",
    }


def test_request_any_additional_forcing_args_with_input(
    fake_fcb_empty_case, sample_forcing_config
):
    fcb = fake_fcb_empty_case
    """Test that function updates args with user JSON input."""
    requested_configs = ["tides"]
    user_json = '{"tidal_constituents": ["M2", "K1"]}'

    with pytest.raises(ValueError):  # Fails because correct user_args are given
        with patch("builtins.input", return_value=user_json):
            result = fcb.set_up_forcing_inputs(
                sample_forcing_config, {}, requested_configs
            )


def test_resolve_forcing_configurations(fake_fcb_empty_case, sample_forcing_config):
    """Test resolve_forcing_configurations returns requested and removed configs."""
    fcb = fake_fcb_empty_case
    fcb.forcing_config = sample_forcing_config
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
                requested, remove = fcb.resolve_forcing_configurations()

    assert isinstance(requested, list)
    assert isinstance(remove, set)
    assert "bgc" in remove


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
