import json
import pytest
from unittest.mock import patch, MagicMock, call
from argparse import Namespace
from pathlib import Path

from CrocoDash.extract_forcings.driver import resolve_components, run_workflow, _load


# =============================================================================
# resolve_components
# =============================================================================


def _make_args(**overrides):
    defaults = dict(
        all=False,
        ic=False,
        bc=False,
        bgcic=False,
        bgcironforcing=False,
        runoff=False,
        bgcrivernutrients=False,
        tides=False,
        chl=False,
        skip=[],
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def test_resolve_components_all_enables_configured_components():
    args = _make_args(all=True)
    config = {"tides": {}, "runoff": {}, "bgcic": {}, "caseroot": "/x", "conditions": {}}
    resolved = resolve_components(args, config)
    assert resolved.tides is True
    assert resolved.runoff is True
    assert resolved.bgcic is True
    assert resolved.chl is False  # not in config


def test_resolve_components_ic_bc_always_available():
    """ic and bc are valid even when not explicit config keys."""
    args = _make_args(all=True)
    config = {"caseroot": "/x", "conditions": {}}
    resolved = resolve_components(args, config)
    assert resolved.ic is True
    assert resolved.bc is True


def test_resolve_components_skip_case_insensitive():
    args = _make_args(all=True, skip=["TIDES", "Runoff"])
    config = {"tides": {}, "runoff": {}, "bgcic": {}}
    resolved = resolve_components(args, config)
    assert resolved.tides is False
    assert resolved.runoff is False
    assert resolved.bgcic is True


def test_resolve_components_missing_in_config_disabled():
    args = _make_args(bgcic=True, runoff=True)
    config = {"bgcic": {}}  # runoff not configured
    resolved = resolve_components(args, config)
    assert resolved.bgcic is True
    assert resolved.runoff is False


def test_resolve_components_individual_flags_no_all():
    args = _make_args(bgcic=True, tides=True)
    config = {"bgcic": {}, "tides": {}, "runoff": {}}
    resolved = resolve_components(args, config)
    assert resolved.bgcic is True
    assert resolved.tides is True
    assert resolved.runoff is False  # not explicitly requested


def test_resolve_components_skip_empty_default():
    args = _make_args(all=True)
    config = {"tides": {}}
    resolved = resolve_components(args, config)
    assert resolved.skip == []


# =============================================================================
# _load
# =============================================================================


def test_load_reads_config_and_state(tmp_path):
    caseroot = tmp_path / "mycase"
    caseroot.mkdir()
    state = {
        "inputdir": str(tmp_path / "input"),
        "supergrid_path": str(tmp_path / "grid.nc"),
        "topo_path": str(tmp_path / "topo.nc"),
        "vgrid_path": str(tmp_path / "vgrid.nc"),
    }
    config = {"caseroot": str(caseroot), "conditions": {"general": {}}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    with patch("CrocoDash.extract_forcings.driver.case_state") as mock_cs:
        mock_cs.read.return_value = state
        loaded_config, loaded_state, inputdir = _load(config_path)

    mock_cs.read.assert_called_once_with(str(caseroot))
    assert loaded_config == config
    assert loaded_state == state
    assert inputdir == Path(tmp_path / "input")


# =============================================================================
# run_workflow
# =============================================================================


def _make_config(caseroot="/case", extra_keys=None):
    cfg = {
        "caseroot": caseroot,
        "conditions": {
            "dates": {"start": "20200101", "end": "20200109", "format": "%Y%m%d"},
            "forcing": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_from_rda",
                "information": {},
            },
            "general": {
                "boundary_number_conversion": {"north": 1, "south": 2},
                "step": "7",
                "preview": False,
            },
        },
    }
    if extra_keys:
        cfg.update(extra_keys)
    return cfg


def _make_state(tmp_path):
    return {
        "inputdir": str(tmp_path),
        "supergrid_path": str(tmp_path / "grid.nc"),
        "topo_path": str(tmp_path / "topo.nc"),
        "vgrid_path": str(tmp_path / "vgrid.nc"),
    }


@patch("CrocoDash.extract_forcings.driver.merge_piecewise_dataset")
@patch("CrocoDash.extract_forcings.driver.regrid_dataset_piecewise")
@patch("CrocoDash.extract_forcings.driver.get_dataset_piecewise")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_ic_bc_calls_piecewise_triple(
    mock_cs, mock_get, mock_regrid, mock_merge, tmp_path
):
    config = _make_config()
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, ic=True, bc=True)

    assert mock_get.called
    assert mock_regrid.called
    assert mock_merge.called


@patch("CrocoDash.extract_forcings.driver.merge_piecewise_dataset")
@patch("CrocoDash.extract_forcings.driver.regrid_dataset_piecewise")
@patch("CrocoDash.extract_forcings.driver.get_dataset_piecewise")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_no_components_returns_early(
    mock_cs, mock_get, mock_regrid, mock_merge, tmp_path, capsys
):
    config = _make_config()
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    result = run_workflow(config_path=config_path)

    assert result is None
    assert not mock_get.called
    captured = capsys.readouterr()
    assert "No components selected" in captured.out


@patch("CrocoDash.extract_forcings.driver.bgc")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_bgcic_calls_bgc_module(mock_cs, mock_bgc, tmp_path):
    config = _make_config(
        extra_keys={
            "bgcic": {
                "inputs": {"marbl_ic_filepath": "/some/file.nc"},
                "outputs": {"MARBL_TRACERS_IC_FILE": "marbl_ic.nc"},
            }
        }
    )
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, bgcic=True)

    mock_bgc.process_bgc_ic.assert_called_once()


@patch("CrocoDash.extract_forcings.driver.rof")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_runoff_calls_rof_module(mock_cs, mock_rof, tmp_path):
    config = _make_config(
        extra_keys={
            "runoff": {
                "inputs": {
                    "rof_grid_name": "r05",
                    "rof_esmf_mesh_filepath": "/m.nc",
                    "case_esmf_mesh_path": "/c.nc",
                    "case_grid_name": "mygrid",
                    "rmax": 0.1,
                    "fold": False,
                }
            }
        }
    )
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, runoff=True)

    mock_rof.generate_rof_ocn_map.assert_called_once()


@patch("CrocoDash.extract_forcings.driver.merge_piecewise_dataset")
@patch("CrocoDash.extract_forcings.driver.regrid_dataset_piecewise")
@patch("CrocoDash.extract_forcings.driver.get_dataset_piecewise")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_returns_timings(mock_cs, mock_get, mock_regrid, mock_merge, tmp_path):
    config = _make_config()
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    result = run_workflow(config_path=config_path, ic=True)

    assert isinstance(result, dict)
    assert "ic/bc" in result
