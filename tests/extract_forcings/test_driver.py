import json
from unittest.mock import patch
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
        ciceic=False,
        ciceobc=False,
        ww3=False,
        skip=[],
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def test_resolve_components_all_enables_configured_components():
    args = _make_args(all=True)
    config = {
        "tides": {},
        "runoff": {},
        "bgcic": {},
        "caseroot": "/x",
        "conditions": {},
    }
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


def test_resolve_components_ww3_flag():
    """--ww3 should only enable when requested and present in config"""
    args = _make_args(ww3=True)
    config = {"ww3": {}}
    resolved = resolve_components(args, config)
    assert resolved.ww3 is True


def test_resolve_components_ww3_missing_in_config_disabled():
    args = _make_args(ww3=True)
    config = {}  # ww3 not configured
    resolved = resolve_components(args, config)
    assert resolved.ww3 is False


def test_resolve_components_skip_empty_default():
    args = _make_args(all=True)
    config = {"tides": {}}
    resolved = resolve_components(args, config)
    assert resolved.skip == []


def test_resolve_components_ciceic_flag():
    """--ciceic should only enable when requested and present in config."""
    args = _make_args(ciceic=True)
    config = {"ciceic": {}}
    resolved = resolve_components(args, config)
    assert resolved.ciceic is True


def test_resolve_components_ciceobc_flag():
    """--ciceobc should only enable when requested and present in config."""
    args = _make_args(ciceobc=True)
    config = {"ciceobc": {}}
    resolved = resolve_components(args, config)
    assert resolved.ciceobc is True


def test_resolve_components_ciceic_missing_in_config_disabled():
    args = _make_args(ciceic=True)
    config = {}
    resolved = resolve_components(args, config)
    assert resolved.ciceic is False


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
            "inputs": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_from_rda",
            },
            "outputs": {
                "start_date": "20200101",
                "end_date": "20200109",
                "date_format": "%Y%m%d",
                "information": {},
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


@patch("CrocoDash.extract_forcings.driver.mom6")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_ic_bc_calls_mom6(mock_cs, mock_mom6, tmp_path):
    config = _make_config()
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, ic=True, bc=True)

    assert mock_mom6.process_mom6_obc.called
    assert mock_mom6.process_mom6_ic.called


@patch("CrocoDash.extract_forcings.driver.mom6")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_no_components_returns_early(mock_cs, mock_mom6, tmp_path, capsys):
    config = _make_config()
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    result = run_workflow(config_path=config_path)

    assert result is None
    assert not mock_mom6.process_mom6_obc.called
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


@patch("CrocoDash.extract_forcings.driver.ww3_mod")
@patch("CrocoDash.extract_forcings.driver.Grid")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_ww3_calls_ww3_module(mock_cs, mock_grid, mock_ww3, tmp_path):
    config = _make_config(
        extra_keys={
            "ww3": {
                "inputs": {
                    "boundaries": ["north", "south"],
                    "ww3_obc_product_name": None,
                    "ww3_obc_function_name": None,
                }
            }
        }
    )
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, ww3=True)

    mock_ww3.process_ww3_obc.assert_called_once()
    _, kwargs = mock_ww3.process_ww3_obc.call_args
    assert kwargs["boundaries"] == ["north", "south"]
    assert kwargs["date_range"] == ("20200101", "20200109")


@patch("CrocoDash.extract_forcings.driver.mom6")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_returns_timings(mock_cs, mock_mom6, tmp_path):
    config = _make_config()
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    result = run_workflow(config_path=config_path, ic=True)

    assert isinstance(result, dict)
    assert "ic" in result


@patch("CrocoDash.extract_forcings.driver.cice")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_ciceic_calls_cice_module(
    mock_cs, mock_cice, tmp_path, gen_grid_topo_vgrid
):
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")
    config = _make_config(
        extra_keys={
            "ciceic": {
                "inputs": {
                    "cice_product_name": "GLORYS",
                    "cice_function_name": "get_glorys_data_from_rda",
                }
            }
        }
    )
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, ciceic=True)

    mock_cice.process_cice_ic.assert_called_once()


@patch("CrocoDash.extract_forcings.driver.cice")
@patch("CrocoDash.extract_forcings.driver.case_state")
def test_run_workflow_ciceobc_calls_cice_module(
    mock_cs, mock_cice, tmp_path, gen_grid_topo_vgrid
):
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")
    config = _make_config(
        extra_keys={
            "ciceobc": {
                "inputs": {
                    "boundaries": ["north", "south"],
                    "cice_product_name": "GLORYS",
                    "cice_function_name": "get_glorys_data_from_rda",
                }
            }
        }
    )
    state = _make_state(tmp_path)
    mock_cs.read.return_value = state
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    run_workflow(config_path=config_path, ciceobc=True)

    mock_cice.process_cice_obc.assert_called_once()
