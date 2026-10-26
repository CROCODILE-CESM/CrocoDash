"""
Unit tests for CrocoDash/recipe.py.

Covers:
- validate_config_structure: valid/invalid variants
- load_config: file I/O + validation round-trip
- read_grids: the grid files a config names
- case_to_yaml: reads state files written by Case.__init__ + configure_forcings
- Round-trip: case_to_yaml output is a valid input for create_case_from_yaml
"""

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


@pytest.fixture(scope="session")
def sample_forcing_config():
    forcing_config = {
        "caseroot": "/fake/case",
        "conditions": {
            "inputs": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_script_for_cli",
                "start_date": "20200101",
                "end_date": "20200109",
            },
            "outputs": {
                "date_format": "%Y%m%d",
                "boundary_number_conversion": {"north": 1},
            },
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


from CrocoDash.recipe import (
    case_to_yaml,
    create_case_from_yaml,
    load_config,
    read_grids,
    validate_config_structure,
)
import CrocoDash.recipe as recipe
from CrocoDash.case import Case
from CrocoDash.case_state import check_version as _check_state_schema_version
from CrocoDash.case_state import SCHEMA_VERSION as STATE_SCHEMA_VERSION
from CrocoDash.forcing.base import CONFIG_FILENAME, write_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _forcing_args(forcing_config, tmp_path):
    """Case.forcing_args() of a case whose config.json is forcing_config."""
    case = Case.__new__(Case)
    case.extract_forcings_path = tmp_path
    case._configure_forcings_called = True
    write_config(tmp_path / CONFIG_FILENAME, forcing_config)
    return case.forcing_args()


CASE_KEYS = (
    "cesmroot",
    "caseroot",
    "inputdir",
    "compset",
    "machine",
    "ocn_grid",
    "ocn_topo",
    "ocn_vgrid",
)

MINIMAL_VALID_CONFIG = {
    "case": {
        "cesmroot": "/cesm",
        "caseroot": "/case",
        "inputdir": "/inputdir",
        "compset": "CR_JRA",
        "machine": "derecho",
        "ocn_grid": "/grids/ocean_hgrid.nc",
        "ocn_topo": "/grids/ocean_topog.nc",
        "ocn_vgrid": "/grids/ocean_vgrid.nc",
    },
    "forcings": {
        "date_range": ["2020-01-01 00:00:00", "2020-12-31 00:00:00"],
        "boundaries": ["north", "south", "east", "west"],
        "product_name": "GLORYS",
        "function_name": "get_glorys_data_from_rda",
    },
}


# ---------------------------------------------------------------------------
# validate_config_structure
# ---------------------------------------------------------------------------


def test_validate_valid_config():
    validate_config_structure(MINIMAL_VALID_CONFIG)


def test_validate_missing_top_level_sections():
    bad = {"forcings": {}}  # no case
    with pytest.raises(ValueError, match="missing required top-level"):
        validate_config_structure(bad)


@pytest.mark.parametrize("missing_key", CASE_KEYS)
def test_validate_missing_case_key(missing_key):
    config = {
        "case": {k: "x" for k in CASE_KEYS if k != missing_key},
        "forcings": {
            "date_range": ["2020-01-01", "2020-02-01"],
            "boundaries": ["north"],
            "product_name": "GLORYS",
            "function_name": "get_glorys",
        },
    }
    with pytest.raises(ValueError, match=f"case\\.{missing_key}"):
        validate_config_structure(config)


def test_validate_forcings_missing_date_range():
    forcings = {
        "boundaries": ["north"],
        "product_name": "GLORYS",
        "function_name": "get_glorys",
    }
    config = {**MINIMAL_VALID_CONFIG, "forcings": forcings}
    with pytest.raises(ValueError, match="forcings\\.date_range"):
        validate_config_structure(config)


def test_validate_forcings_bad_date_range_not_list():
    config = {
        **MINIMAL_VALID_CONFIG,
        "forcings": {
            "date_range": "2020-01-01",
            "boundaries": ["north"],
            "product_name": "GLORYS",
            "function_name": "get_glorys",
        },
    }
    with pytest.raises(ValueError, match="date_range must be a list"):
        validate_config_structure(config)


def test_validate_forcings_bad_date_range_wrong_length():
    config = {
        **MINIMAL_VALID_CONFIG,
        "forcings": {
            "date_range": ["2020-01-01"],
            "boundaries": ["north"],
            "product_name": "GLORYS",
            "function_name": "get_glorys",
        },
    }
    with pytest.raises(ValueError, match="date_range must be a list"):
        validate_config_structure(config)


def test_validate_forcings_invalid_boundary():
    config = {
        **MINIMAL_VALID_CONFIG,
        "forcings": {
            "date_range": ["2020-01-01", "2020-02-01"],
            "boundaries": ["northwest"],
            "product_name": "GLORYS",
            "function_name": "get_glorys",
        },
    }
    with pytest.raises(ValueError, match="Invalid boundary"):
        validate_config_structure(config)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_valid_file(tmp_path):
    config_file = tmp_path / "case.yaml"
    config_file.write_text(yaml.dump(MINIMAL_VALID_CONFIG))
    loaded = load_config(config_file)
    assert loaded["case"]["ocn_grid"] == "/grids/ocean_hgrid.nc"
    assert loaded["case"]["machine"] == "derecho"


def test_load_config_invalid_file_raises(tmp_path):
    bad = {"grid": {}, "topo": {}}
    config_file = tmp_path / "bad.yaml"
    config_file.write_text(yaml.dump(bad))
    with pytest.raises(ValueError):
        load_config(config_file)


# ---------------------------------------------------------------------------
# read_grids
# ---------------------------------------------------------------------------


def test_read_grids_keeps_the_grid_name_and_min_depth(gen_grid_topo_vgrid, tmp_path):
    """The grid keeps the name it was written with, not its file's name. A case
    names its grid files and some forcing files after it, so a case created
    from another needs it to reuse the source's files."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    paths = [tmp_path / f"{kind}_{grid.name}_abc123.nc" for kind in ("h", "t", "v")]
    grid.write_supergrid(paths[0])
    topo.write_topo(paths[1])
    vgrid.write(paths[2])

    read_grid, read_topo, read_vgrid = read_grids(*paths)

    assert read_grid.name == grid.name
    assert read_topo.min_depth == topo.min_depth
    assert read_vgrid.nk == vgrid.nk


# ---------------------------------------------------------------------------
# _check_state_schema_version
# ---------------------------------------------------------------------------

FAKE_PATH = "/some/case/_crocodash_state.json"

_major, _minor, _patch = STATE_SCHEMA_VERSION.split(".")


@pytest.mark.parametrize(
    "state, raises, match",
    [
        ({"schema_version": STATE_SCHEMA_VERSION}, None, None),
        ({"schema_version": f"{_major}.{_minor}.99"}, None, None),
        ({}, ValueError, None),
        (
            {"schema_version": f"{_major}.{int(_minor) + 1}.{_patch}"},
            ValueError,
            "schema version",
        ),
        (
            {"schema_version": f"{int(_major) + 1}.{_minor}.{_patch}"},
            ValueError,
            "schema version",
        ),
        ({"schema_version": "not-a-version"}, ValueError, "Invalid schema_version"),
    ],
)
def test_check_state_schema_version(state, raises, match):
    if raises:
        with pytest.raises(raises, match=match):
            _check_state_schema_version(state, FAKE_PATH)
    else:
        _check_state_schema_version(state, FAKE_PATH)


# ---------------------------------------------------------------------------
# case_to_yaml
# ---------------------------------------------------------------------------


def test_case_to_yaml_missing_state_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="crocodash_state\\.json"):
        case_to_yaml(tmp_path / "no_case_here")


def test_case_to_yaml_structure(get_CrocoDash_case):
    case = get_CrocoDash_case
    config = case_to_yaml(case.caseroot)

    assert set(config.keys()) >= {"case"}
    for key in CASE_KEYS:
        assert key in config["case"]


def test_case_to_yaml_values_match_case(get_CrocoDash_case):
    case = get_CrocoDash_case
    config = case_to_yaml(case.caseroot)

    assert config["case"]["compset"] == case.compset_lname
    assert config["case"]["machine"] == case.machine
    assert config["case"]["caseroot"] == str(case.caseroot)
    assert config["case"]["inputdir"] == str(case.inputdir)
    assert config["case"]["ocn_grid"] == case.supergrid_path


def test_case_to_yaml_with_forcings(get_case_with_cf):
    case = get_case_with_cf
    config = case_to_yaml(case.caseroot)

    assert "forcings" in config
    assert "date_range" in config["forcings"]
    assert "boundaries" in config["forcings"]
    assert "product_name" in config["forcings"]
    assert "function_name" in config["forcings"]
    assert isinstance(config["forcings"]["date_range"], list)
    assert len(config["forcings"]["date_range"]) == 2


# ---------------------------------------------------------------------------
# Round-trip: case_to_yaml output is valid input for create_case_from_yaml
# ---------------------------------------------------------------------------


def test_case_to_yaml_round_trip_is_valid_config(get_case_with_cf):
    """case_to_yaml output must pass validate_config_structure without error."""
    case = get_case_with_cf
    config = case_to_yaml(case.caseroot)
    validate_config_structure(config)


def test_case_to_yaml_round_trip(get_case_with_cf, tmp_path):
    """case_to_yaml output can be written to YAML and reloaded identically, including forcings."""
    case = get_case_with_cf
    config = case_to_yaml(case.caseroot)

    yaml_path = tmp_path / "round_trip.yaml"
    yaml_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
    reloaded = yaml.safe_load(yaml_path.read_text())

    assert reloaded["case"]["compset"] == config["case"]["compset"]
    assert reloaded["case"]["machine"] == config["case"]["machine"]
    for key in ("ocn_grid", "ocn_topo", "ocn_vgrid"):
        assert reloaded["case"][key] == config["case"][key]
    assert reloaded["forcings"]["date_range"] == config["forcings"]["date_range"]
    assert reloaded["forcings"]["boundaries"] == config["forcings"]["boundaries"]
    assert reloaded["forcings"]["product_name"] == config["forcings"]["product_name"]


def test_build_general_configure_forcing_args(sample_forcing_config, tmp_path):
    """Test Case.forcing_args creates correct argument dict."""
    args = _forcing_args(sample_forcing_config, tmp_path)

    assert args["date_range"] == ["2020-01-01 00:00:00", "2020-01-09 00:00:00"]
    assert args["boundaries"] == ["north"]
    assert args["product_name"] == "GLORYS"
    assert args["function_name"] == "get_glorys_data_script_for_cli"
    assert args["tidal_constituents"] == ["M2", "K1"]
    assert "case_specific_param" not in args


def test_configure_forcing_args_round_trip_optional_args(
    sample_forcing_config, tmp_path
):
    """Configurators whose constructor args all carry defaults must still be
    round-tripped. CICE is the case in point: every one of its args is
    optional, so a required-args-only walk returned nothing and a forked case
    came back with no CICE forcing configured at all."""
    forcing_config = copy.deepcopy(sample_forcing_config)
    forcing_config["cice"] = {
        "inputs": {
            "cice_product_name": "cice_restart",
            "cice_function_name": "get_cice_restart_subset",
            "cice_function_args": {
                "restart_path": "/fake/restart.nc",
                "grid_path": "/fake/grid.nc",
            },
            # non-default value: silently reverting to the default of True
            # would turn restoring back on for the reproduced case
            "restore_ice": False,
        }
    }

    args = _forcing_args(forcing_config, tmp_path)

    assert args["cice_product_name"] == "cice_restart"
    assert args["cice_function_name"] == "get_cice_restart_subset"
    assert args["cice_function_args"] == {
        "restart_path": "/fake/restart.nc",
        "grid_path": "/fake/grid.nc",
    }
    assert args["restore_ice"] is False


def test_configure_forcing_args_conditions_boundaries_win(
    sample_forcing_config, tmp_path
):
    """The conditions block is the authority on boundaries; a configurator's own
    stored copy must not overwrite it."""
    forcing_config = copy.deepcopy(sample_forcing_config)
    forcing_config["tides"]["inputs"]["boundaries"] = ["south"]

    args = _forcing_args(forcing_config, tmp_path)

    assert args["boundaries"] == ["north"]


def test_configure_forcing_args_keeps_function_overrides(
    sample_forcing_config, tmp_path
):
    """Access-method arguments the user changed survive dump/fork; the ones
    still at their defaults are left out."""
    forcing_config = copy.deepcopy(sample_forcing_config)
    forcing_config["conditions"]["inputs"].update(
        function_name="get_glorys_data_from_rda",
        function_args={"buf": 2.0, "name": None},
    )

    args = _forcing_args(forcing_config, tmp_path)

    assert args["function_overrides"] == {"buf": 2.0}


def test_configure_forcing_args_missing_required_arg_raises(
    sample_forcing_config, tmp_path
):
    forcing_config = copy.deepcopy(sample_forcing_config)
    del forcing_config["bgcic"]["inputs"]["marbl_ic_filepath"]

    with pytest.raises(ValueError, match="marbl_ic_filepath"):
        _forcing_args(forcing_config, tmp_path)


def test_a_case_from_another_on_a_new_machine_drops_its_machine_settings(
    monkeypatch, tmp_path
):
    """The new case keeps the source's session id, so the source's grid and
    forcing files apply unrenamed, but not how the source runs on its own
    machine: its PE layout and batch job."""
    created = {}

    class FakeCase:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.machine, self.caseroot = kwargs["machine"], kwargs["caseroot"]

        def apply_user_changes(self, changes):
            pass

        def configure_forcings(self, **kwargs):
            pass

        def copy_forcing_files(self, source):
            return []

    monkeypatch.setattr(recipe, "Case", FakeCase)
    monkeypatch.setattr(recipe, "read_grids", lambda *paths: (None, None, None))
    no_changes = dict(caseroot="/src/case", xmlchanges={}, user_nl={})
    source = SimpleNamespace(
        machine="derecho",
        session_id="abc123",
        caseroot=Path("/src/case"),
        inputdir=Path("/src/input"),
        bundled_from=None,
        user_changes=lambda target_machine=None: copy.deepcopy(
            no_changes | dict(source_mods=[], xml_files=[])
        ),
    )
    case = {"caseroot": str(tmp_path / "new"), "inputdir": str(tmp_path / "in")}
    case |= {"machine": "ubuntu-latest", "ntasks_ocn": 128, "job_queue": "main"}
    case |= {"ocn_grid": "h.nc", "ocn_topo": "t.nc", "ocn_vgrid": "v.nc"}
    config = {"case": case, "forcings": {}}

    create_case_from_yaml(config, configure_only=True, source=source)

    assert created["session_id"] == "abc123"
    assert "ntasks_ocn" not in created and "job_queue" not in created
