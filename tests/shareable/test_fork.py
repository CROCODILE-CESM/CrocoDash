from CrocoDash.shareable import *
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


@pytest.fixture
def fake_fcb_empty_case():
    fcb = ForkBundle.__new__(ForkBundle)
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

    with patch("CrocoDash.shareable.ask_yes_no", return_value=True):
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


def test_configure_yaml_for_forked_case_args(fake_fcb_empty_case, tmp_path):
    """Test _configure_yaml_for_forked_case_args correctly patches destination fields."""
    fcb = fake_fcb_empty_case
    fcb.bundle_location = tmp_path / "bundle"
    (fcb.bundle_location / "ocnice").mkdir(parents=True)

    bundle_yaml = {
        "case": {
            "cesmroot": "/old/cesm",
            "machine": "old_machine",
            "project": "OLD123",
            "caseroot": "/old/case",
            "inputdir": "/old/inputdir",
            "compset": "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV",
        },
        "grid": {"supergrid_path": "/old/ocnice/ocean_hgrid.nc"},
        "topo": {
            "source": {
                "type": "from_file",
                "topo_file_path": "/old/ocnice/ocean_topog.nc",
            }
        },
        "vgrid": {"type": "from_file", "filename": "/old/ocnice/ocean_vgrid.nc"},
    }
    fcb.bundle_yaml = bundle_yaml

    config = fcb._configure_yaml_for_forked_case_args(
        cesmroot="/new/cesm",
        machine="new_machine",
        project_number="NEW123",
        new_caseroot="/new/case",
        new_inputdir="/new/inputdir",
    )

    assert config["case"]["cesmroot"] == "/new/cesm"
    assert config["case"]["machine"] == "new_machine"
    assert config["case"]["project"] == "NEW123"
    assert config["case"]["caseroot"] == "/new/case"
    assert config["case"]["inputdir"] == "/new/inputdir"
    # Original must be unchanged
    assert bundle_yaml["case"]["cesmroot"] == "/old/cesm"
    # Grid/topo/vgrid paths are redirected to bundle ocnice
    assert "ocean_hgrid.nc" in config["grid"]["supergrid_path"]
    assert "ocean_topog.nc" in config["topo"]["source"]["topo_file_path"]
    assert "ocean_vgrid.nc" in config["vgrid"]["filename"]


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


