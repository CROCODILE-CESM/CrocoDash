"""
Unit tests for CrocoDash/recipe.py.

Covers:
- validate_config_structure: valid/invalid variants
- load_config: file I/O + validation round-trip
- build_grid / build_topo / build_vgrid: each source type
- case_to_yaml: reads state files written by Case.__init__ + configure_forcings
- Round-trip: case_to_yaml output is a valid input for create_case_from_yaml
"""

import json
import pytest
import yaml
from pathlib import Path

from CrocoDash.recipe import (
    build_grid,
    build_topo,
    build_vgrid,
    case_to_yaml,
    load_config,
    validate_config_structure,
)
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_VALID_CONFIG = {
    "grid": {
        "lenx": 4.0,
        "leny": 3.0,
        "resolution": 0.1,
        "xstart": 278.0,
        "ystart": 7.0,
    },
    "topo": {
        "min_depth": 9.5,
        "source": {"type": "flat", "depth": 100.0},
    },
    "vgrid": {"type": "uniform", "nk": 10, "depth": 100.0},
    "case": {
        "cesmroot": "/cesm",
        "caseroot": "/case",
        "inputdir": "/inputdir",
        "compset": "CR_JRA",
        "machine": "derecho",
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
    bad = {"grid": {}, "topo": {}}  # no vgrid, no case
    with pytest.raises(ValueError, match="missing required top-level"):
        validate_config_structure(bad)


@pytest.mark.parametrize(
    "missing_key", ["cesmroot", "caseroot", "inputdir", "compset", "machine"]
)
def test_validate_missing_case_key(missing_key):
    config = {
        "grid": {},
        "topo": {},
        "vgrid": {"type": "uniform"},
        "case": {
            k: "x"
            for k in ("cesmroot", "caseroot", "inputdir", "compset", "machine")
            if k != missing_key
        },
        "forcings": {
            "date_range": ["2020-01-01", "2020-02-01"],
            "boundaries": ["north"],
            "product_name": "GLORYS",
            "function_name": "get_glorys",
        },
    }
    with pytest.raises(ValueError, match=f"case\\.{missing_key}"):
        validate_config_structure(config)


def test_validate_invalid_topo_type():
    config = {**MINIMAL_VALID_CONFIG, "topo": {"source": {"type": "bogus"}}}
    with pytest.raises(ValueError, match="topo\\.source\\.type"):
        validate_config_structure(config)


def test_validate_invalid_vgrid_type():
    config = {**MINIMAL_VALID_CONFIG, "vgrid": {"type": "bogus"}}
    with pytest.raises(ValueError, match="vgrid\\.type"):
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
    assert loaded["vgrid"]["type"] == "uniform"
    assert loaded["case"]["machine"] == "derecho"


def test_load_config_invalid_file_raises(tmp_path):
    bad = {"grid": {}, "topo": {}}
    config_file = tmp_path / "bad.yaml"
    config_file.write_text(yaml.dump(bad))
    with pytest.raises(ValueError):
        load_config(config_file)


# ---------------------------------------------------------------------------
# build_grid
# ---------------------------------------------------------------------------


def test_build_grid_from_params():
    cfg = {
        "lenx": 4.0,
        "leny": 3.0,
        "resolution": 0.5,
        "xstart": 278.0,
        "ystart": 7.0,
        "name": "testgrid",
    }
    grid = build_grid(cfg)
    assert isinstance(grid, Grid)
    assert grid.name == "testgrid"
    assert grid.lenx == pytest.approx(4.0, rel=0.01)
    assert grid.leny == pytest.approx(3.0, rel=0.01)


def test_build_grid_from_supergrid_file(gen_grid_topo_vgrid, tmp_path):
    orig_grid, _, _ = gen_grid_topo_vgrid
    supergrid_path = tmp_path / "ocean_hgrid.nc"
    orig_grid.write_supergrid(supergrid_path)

    cfg = {"supergrid_path": str(supergrid_path), "name": "reloaded"}
    grid = build_grid(cfg)
    assert isinstance(grid, Grid)
    assert grid.name == "reloaded"
    assert grid.nx == orig_grid.nx
    assert grid.ny == orig_grid.ny


def test_build_grid_from_supergrid_preserves_shape(gen_grid_topo_vgrid, tmp_path):
    orig_grid, _, _ = gen_grid_topo_vgrid
    supergrid_path = tmp_path / "ocean_hgrid.nc"
    orig_grid.write_supergrid(supergrid_path)

    grid = build_grid({"supergrid_path": str(supergrid_path)})
    assert grid.nx == orig_grid.nx
    assert grid.ny == orig_grid.ny


# ---------------------------------------------------------------------------
# build_topo
# ---------------------------------------------------------------------------


def test_build_topo_flat(get_rect_grid):
    cfg = {"min_depth": 9.5, "source": {"type": "flat", "depth": 500.0}}
    topo = build_topo(cfg, get_rect_grid)
    assert isinstance(topo, Topo)
    assert topo.max_depth == pytest.approx(500.0, rel=0.01)
    assert topo.min_depth == pytest.approx(9.5, rel=0.01)


def test_build_topo_from_file(gen_grid_topo_vgrid, tmp_path):
    grid, orig_topo, _ = gen_grid_topo_vgrid
    topo_path = tmp_path / "ocean_topog.nc"
    orig_topo.write_topo(topo_path)

    cfg = {
        "min_depth": orig_topo.min_depth,
        "source": {"type": "from_file", "topo_file_path": str(topo_path)},
    }
    topo = build_topo(cfg, grid)
    assert isinstance(topo, Topo)
    assert topo.max_depth == pytest.approx(orig_topo.max_depth, rel=0.01)


def test_build_topo_unknown_type_raises(get_rect_grid):
    cfg = {"min_depth": 9.5, "source": {"type": "unknown"}}
    with pytest.raises(ValueError, match="Unknown topo\\.source\\.type"):
        build_topo(cfg, get_rect_grid)


# ---------------------------------------------------------------------------
# build_vgrid
# ---------------------------------------------------------------------------


def test_build_vgrid_uniform(get_rect_grid_and_topo):
    _, topo = get_rect_grid_and_topo
    cfg = {"type": "uniform", "nk": 10, "depth": 200.0}
    vgrid = build_vgrid(cfg, topo)
    assert isinstance(vgrid, VGrid)
    assert vgrid.nk == 10
    assert vgrid.depth == pytest.approx(200.0, rel=0.01)


def test_build_vgrid_hyperbolic(get_rect_grid_and_topo):
    _, topo = get_rect_grid_and_topo
    cfg = {"type": "hyperbolic", "nk": 20, "depth": 1000.0, "ratio": 10.0}
    vgrid = build_vgrid(cfg, topo)
    assert isinstance(vgrid, VGrid)
    assert vgrid.nk == 20


def test_build_vgrid_depth_defaults_to_topo_max_depth(get_rect_grid_and_topo):
    _, topo = get_rect_grid_and_topo
    cfg = {"type": "uniform", "nk": 5}  # no depth key
    vgrid = build_vgrid(cfg, topo)
    assert vgrid.depth == pytest.approx(topo.max_depth, rel=0.01)


def test_build_vgrid_from_file(get_vgrid, tmp_path):
    vgrid_path = tmp_path / "vgrid.nc"
    get_vgrid.write(vgrid_path)

    cfg = {"type": "from_file", "filename": str(vgrid_path)}
    vgrid = build_vgrid(cfg, topo=None)
    assert isinstance(vgrid, VGrid)
    assert vgrid.nk == get_vgrid.nk
    assert vgrid.depth == pytest.approx(get_vgrid.depth, rel=0.01)


def test_build_vgrid_unknown_type_raises(get_rect_grid_and_topo):
    _, topo = get_rect_grid_and_topo
    with pytest.raises(ValueError, match="Unknown vgrid\\.type"):
        build_vgrid({"type": "bogus", "nk": 5}, topo)


# ---------------------------------------------------------------------------
# case_to_yaml
# ---------------------------------------------------------------------------


def test_case_to_yaml_missing_state_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="crocodash_state\\.json"):
        case_to_yaml(tmp_path / "no_case_here")


def test_case_to_yaml_structure(get_CrocoDash_case):
    case = get_CrocoDash_case
    config = case_to_yaml(case.caseroot)

    assert set(config.keys()) >= {"grid", "topo", "vgrid", "case"}
    assert "supergrid_path" in config["grid"]
    assert "min_depth" in config["topo"]
    assert config["topo"]["source"]["type"] == "from_file"
    assert config["vgrid"]["type"] == "from_file"
    assert "cesmroot" in config["case"]
    assert "caseroot" in config["case"]
    assert "inputdir" in config["case"]
    assert "compset" in config["case"]
    assert "machine" in config["case"]


def test_case_to_yaml_values_match_case(get_CrocoDash_case):
    case = get_CrocoDash_case
    config = case_to_yaml(case.caseroot)

    assert config["case"]["compset"] == case.compset_lname
    assert config["case"]["machine"] == case.machine
    assert config["case"]["caseroot"] == str(case.caseroot)
    assert config["case"]["inputdir"] == str(case.inputdir)
    assert config["grid"]["supergrid_path"] == case.supergrid_path


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
    assert reloaded["grid"]["supergrid_path"] == config["grid"]["supergrid_path"]
    assert (
        reloaded["topo"]["source"]["topo_file_path"]
        == config["topo"]["source"]["topo_file_path"]
    )
    assert reloaded["vgrid"]["filename"] == config["vgrid"]["filename"]
    assert reloaded["forcings"]["date_range"] == config["forcings"]["date_range"]
    assert reloaded["forcings"]["boundaries"] == config["forcings"]["boundaries"]
    assert reloaded["forcings"]["product_name"] == config["forcings"]["product_name"]
