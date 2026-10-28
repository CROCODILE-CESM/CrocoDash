from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from CrocoDash.forcing.base import (
    BaseConfigurator,
    ConfigOutputParam,
    InputValueParam,
    register,
)
from CrocoDash.forcing.driver import resolve_components, run_workflow

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


@register
class _DummyChainAConfigurator(BaseConfigurator):
    """chaina -> chainb -> chainc, to exercise multi-level auto-enable/order."""

    name = "dummychaina"
    process_components = {"chaina": "process"}
    depends_on_outputs = {"dummychainb": ["out"]}
    input_params = []
    output_params = []

    def __init__(self):
        super().__init__()

    def configure(self):
        pass

    def process(self, ctx):
        _CHAIN_CALLS.append("chaina")


@register
class _DummyChainBConfigurator(BaseConfigurator):
    name = "dummychainb"
    process_components = {"chainb": "process"}
    depends_on_outputs = {"dummychainc": ["out"]}
    input_params = []
    output_params = [ConfigOutputParam("out")]

    def __init__(self):
        super().__init__()

    def configure(self):
        pass

    def process(self, ctx):
        _CHAIN_CALLS.append("chainb")


@register
class _DummyChainCConfigurator(BaseConfigurator):
    name = "dummychainc"
    process_components = {"chainc": "process"}
    input_params = []
    output_params = [ConfigOutputParam("out")]

    def __init__(self):
        super().__init__()

    def configure(self):
        pass

    def process(self, ctx):
        _CHAIN_CALLS.append("chainc")


_CHAIN_CALLS = []


def _case(extra_keys=None):
    """What run_workflow() uses of a Case: the context for its config.json."""
    config = {"caseroot": "/x", **(extra_keys or {})}
    return SimpleNamespace(workflow_context=lambda: SimpleNamespace(config=config))


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


def test_run_workflow_dispatches_by_flag():
    _DummyDriverConfigurator.calls.clear()
    case = _case(
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}}
        },
    )

    run_workflow(case, dummyflag=True)

    assert len(_DummyDriverConfigurator.calls) == 1


def test_run_workflow_skips_unrequested_flag():
    _DummyDriverConfigurator.calls.clear()
    case = _case(
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}}
        },
    )

    run_workflow(case, dummyflag=False)

    assert len(_DummyDriverConfigurator.calls) == 0


def test_run_workflow_stops_before_anything_on_a_missing_input_file():
    """Every selected step's input files are checked first, so a run doesn't
    stop at a missing one after the steps before it."""
    _DummyDriverConfigurator.calls.clear()
    case = _case(
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}},
            # Chl reads a chlorophyll file (an InputFileParam).
            "chl": {
                "name": "chl",
                "inputs": {
                    "chl_processed_filepath": "/no/such/file.nc",
                    "case_grid_name": "g",
                    "case_session_id": "s",
                    "calendar": None,
                },
                "outputs": {},
            },
        },
    )

    with pytest.raises(FileNotFoundError, match="/no/such/file.nc"):
        run_workflow(case, dummyflag=True, chl=True)

    assert _DummyDriverConfigurator.calls == []


def test_run_workflow_one_to_many_dispatch():
    _DummyMultiFlagConfigurator.calls.clear()
    case = _case(
        extra_keys={
            "dummymulti": {"name": "dummymulti", "inputs": {}, "outputs": {}},
        },
    )

    run_workflow(case, dummya=True, dummyb=True)

    tags = {tag for tag, _ in _DummyMultiFlagConfigurator.calls}
    assert tags == {"a", "b"}


def test_run_workflow_no_components_returns_early(capsys):
    case = _case()

    result = run_workflow(case)

    assert result is None
    captured = capsys.readouterr()
    assert "No components selected" in captured.out


def test_run_workflow_returns_timings():
    _DummyDriverConfigurator.calls.clear()
    case = _case(
        extra_keys={
            "dummydriver": {"name": "dummydriver", "inputs": {"x": "1"}, "outputs": {}}
        },
    )

    result = run_workflow(case, dummyflag=True)

    assert isinstance(result, dict)
    assert "dummyflag" in result


def test_run_workflow_auto_enables_dependency(tmp_path):
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

    case = _case(
        extra_keys={
            "runoff": {
                "name": "Runoff",
                "inputs": {
                    "case_grid_name": "g",
                    "case_session_id": "s",
                    "case_compset_lname": "DROF",
                    "case_inputdir": str(tmp_path),
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
                    "calendar": {
                        "cf": "noleap",
                        "cesm": "NO_LEAP",
                        "mom6": "noleap",
                    },
                },
                "outputs": {"READ_RIV_FLUXES": "True", "RIV_FLUX_FILE": "riv.nc"},
            },
        },
    )

    with patch.object(RunoffConfigurator, "process", fake_runoff_process), patch.object(
        BGCRiverNutrientsConfigurator, "process", fake_bgcriv_process
    ):
        run_workflow(case, bgcrivernutrients=True)

    # runoff must run before bgcrivernutrients, and be auto-enabled even
    # though it wasn't explicitly requested.
    assert calls == ["runoff", "bgcrivernutrients"]


def test_run_workflow_auto_enables_multi_level_chain():
    """Requesting chaina (which needs chainb, which needs chainc) must
    auto-enable both ancestors and run them in dependency order, regardless
    of PYTHONHASHSEED -- a set was previously used to build the order, which
    made it non-deterministic, and the auto-enable loop only walked one
    level deep."""
    _CHAIN_CALLS.clear()
    case = _case(
        extra_keys={
            "dummychaina": {"name": "dummychaina", "inputs": {}, "outputs": {}},
            "dummychainb": {
                "name": "dummychainb",
                "inputs": {},
                "outputs": {"out": "b"},
            },
            "dummychainc": {
                "name": "dummychainc",
                "inputs": {},
                "outputs": {"out": "c"},
            },
        },
    )

    run_workflow(case, chaina=True)

    assert _CHAIN_CALLS == ["chainc", "chainb", "chaina"]
