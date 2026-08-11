import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from CrocoDash.forcing.base import BaseConfigurator, InputValueParam, register
from CrocoDash.forcing.driver import _load, resolve_components, run_workflow


# =============================================================================
# Dummy configurators exercising the generic process_components dispatch
# =============================================================================


@register
class _DummyDriverConfigurator(BaseConfigurator):
    name = "dummydriver"
    process_components = {"dummyflag": "process"}
    input_params = [InputValueParam("x", comment="dummy")]
    output_params = []

    def __init__(self, x="1"):
        super().__init__(x=x)

    def configure(self):
        pass

    def process(self, ctx):
        _DummyDriverConfigurator.calls.append(ctx)


_DummyDriverConfigurator.calls = []


@register
class _DummyMultiFlagConfigurator(BaseConfigurator):
    """One configurator answering two flags -- exercises the one-to-many case."""

    name = "dummymulti"
    process_components = {"dummya": "process_a", "dummyb": "process_b"}
    input_params = []
    output_params = []

    def __init__(self):
        super().__init__()

    def configure(self):
        pass

    def process_a(self, ctx):
        _DummyMultiFlagConfigurator.calls.append(("a", ctx))

    def process_b(self, ctx):
        _DummyMultiFlagConfigurator.calls.append(("b", ctx))


_DummyMultiFlagConfigurator.calls = []


def _make_state(tmp_path):
    return {
        "inputdir": str(tmp_path),
        "supergrid_path": str(tmp_path / "grid.nc"),
        "topo_path": str(tmp_path / "topo.nc"),
        "vgrid_path": str(tmp_path / "vgrid.nc"),
    }


def _write_config(tmp_path, extra_keys=None):
    config = {"caseroot": str(tmp_path)}
    if extra_keys:
        config.update(extra_keys)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return config_path


# =============================================================================
# resolve_components
# =============================================================================


def _make_args(**overrides):
    defaults = dict(all=False, dummyflag=False, skip=[])
    defaults.update(overrides)
    return Namespace(**defaults)


def test_resolve_components_generic_exists_check():
    args = _make_args(all=True)
    config = {
        "caseroot": "/x",
        "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}},
    }
    resolved = resolve_components(args, config)
    assert resolved.dummyflag is True


def test_resolve_components_missing_from_config_disabled():
    args = _make_args(all=True)
    config = {"caseroot": "/x"}  # dummydriver not present
    resolved = resolve_components(args, config)
    assert resolved.dummyflag is False


def test_resolve_components_skip_case_insensitive():
    args = _make_args(all=True, skip=["DUMMYFLAG"])
    config = {
        "caseroot": "/x",
        "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}},
    }
    resolved = resolve_components(args, config)
    assert resolved.dummyflag is False


# =============================================================================
# run_workflow
# =============================================================================


@patch("CrocoDash.forcing.driver.case_state")
def test_run_workflow_dispatches_by_flag(mock_cs, tmp_path):
    _DummyDriverConfigurator.calls.clear()
    mock_cs.read.return_value = _make_state(tmp_path)
    config_path = _write_config(
        tmp_path,
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}}
        },
    )

    run_workflow(config_path=config_path, dummyflag=True)

    assert len(_DummyDriverConfigurator.calls) == 1


@patch("CrocoDash.forcing.driver.case_state")
def test_run_workflow_skips_unrequested_flag(mock_cs, tmp_path):
    _DummyDriverConfigurator.calls.clear()
    mock_cs.read.return_value = _make_state(tmp_path)
    config_path = _write_config(
        tmp_path,
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}}
        },
    )

    run_workflow(config_path=config_path, dummyflag=False)

    assert len(_DummyDriverConfigurator.calls) == 0


@patch("CrocoDash.forcing.driver.case_state")
def test_run_workflow_one_to_many_dispatch(mock_cs, tmp_path):
    _DummyMultiFlagConfigurator.calls.clear()
    mock_cs.read.return_value = _make_state(tmp_path)
    config_path = _write_config(
        tmp_path,
        extra_keys={
            "dummymulti": {"name": "dummymulti", "inputs": {}, "outputs": {}},
        },
    )

    run_workflow(config_path=config_path, dummya=True, dummyb=True)

    tags = {tag for tag, _ in _DummyMultiFlagConfigurator.calls}
    assert tags == {"a", "b"}


@patch("CrocoDash.forcing.driver.case_state")
def test_run_workflow_no_components_returns_early(mock_cs, tmp_path, capsys):
    mock_cs.read.return_value = _make_state(tmp_path)
    config_path = _write_config(tmp_path)

    result = run_workflow(config_path=config_path)

    assert result is None
    captured = capsys.readouterr()
    assert "No components selected" in captured.out


@patch("CrocoDash.forcing.driver.case_state")
def test_run_workflow_returns_timings(mock_cs, tmp_path):
    _DummyDriverConfigurator.calls.clear()
    mock_cs.read.return_value = _make_state(tmp_path)
    config_path = _write_config(
        tmp_path,
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}}
        },
    )

    result = run_workflow(config_path=config_path, dummyflag=True)

    assert isinstance(result, dict)
    assert "dummyflag" in result


@patch("CrocoDash.forcing.driver.case_state")
def test_run_workflow_auto_enables_dependency(mock_cs, tmp_path):
    """bgcrivernutrients auto-enables runoff -- the one documented exception
    to fully-generic dispatch (see _PROCESS_ORDER_OVERRIDES)."""
    from CrocoDash.forcing.runoff import RunoffConfigurator
    from CrocoDash.forcing.bgc import BGCRiverNutrientsConfigurator

    calls = []
    src = tmp_path / "river.nc"
    src.write_bytes(b"x")

    def fake_runoff_process(self, ctx):
        calls.append("runoff")

    def fake_bgcriv_process(self, ctx):
        calls.append("bgcrivernutrients")

    mock_cs.read.return_value = _make_state(tmp_path)
    config_path = _write_config(
        tmp_path,
        extra_keys={
            "runoff": {
                "name": "Runoff",
                "inputs": {
                    "case_grid_name": "g",
                    "case_session_id": "s",
                    "case_compset_lname": "DROF",
                    "case_inputdir": str(tmp_path),
                    "case_is_non_local": False,
                    "case_esmf_mesh_path": "/fake.nc",
                    "rmax": 20,
                    "fold": 40,
                    "rof_grid_name": "GLOFAS",
                    "rof_esmf_mesh_filepath": "/fake2.nc",
                },
                "outputs": {"ROF2OCN_LIQ_RMAPNAME": None, "ROF2OCN_ICE_RMAPNAME": None},
            },
            "bgcrivernutrients": {
                "name": "BGCRiverNutrients",
                "inputs": {
                    "global_river_nutrients_filepath": str(src),
                    "case_session_id": "s",
                    "case_grid_name": "g",
                    "cf_calendar": "noleap",
                },
                "outputs": {"READ_RIV_FLUXES": "True", "RIV_FLUX_FILE": "riv.nc"},
            },
        },
    )

    with patch.object(RunoffConfigurator, "process", fake_runoff_process), patch.object(
        BGCRiverNutrientsConfigurator, "process", fake_bgcriv_process
    ):
        run_workflow(config_path=config_path, bgcrivernutrients=True)

    # runoff must run before bgcrivernutrients, and be auto-enabled even
    # though it wasn't explicitly requested.
    assert calls == ["runoff", "bgcrivernutrients"]
