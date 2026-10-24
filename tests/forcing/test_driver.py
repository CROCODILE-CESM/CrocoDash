from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from CrocoDash.forcing.base import (
    BaseConfigurator,
    ConfigOutputParam,
    InputValueParam,
    register,
)
from CrocoDash.forcing.driver import (
    portable_settings,
    resolve_components,
    run_workflow,
)

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


@register
class _DummyFilesConfigurator(BaseConfigurator):
    """Declares one file, which process() writes, noting whether it was
    already there. dummyfiles_x has no default, so the registry never
    activates this class in a real case."""

    name = "dummyfiles"
    process_components = {"dummyfiles": "process"}
    input_params = [InputValueParam("dummyfiles_x", comment="dummy")]
    output_params = []
    existed = []

    def __init__(self, dummyfiles_x):
        super().__init__(dummyfiles_x=dummyfiles_x)

    def configure(self):
        pass

    def output_files(self, ctx):
        return {"dummyfiles": [ctx.output_path / "dummy.nc"]}

    def process(self, ctx):
        path = ctx.output_path / "dummy.nc"
        _DummyFilesConfigurator.existed.append(path.exists())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def _case(extra_keys=None, inputdir="/x/input"):
    """What run_workflow() uses of a Case: its cesmroot and the context for
    its config.json."""
    config = {"caseroot": "/x", **(extra_keys or {})}
    ctx = SimpleNamespace(
        config=config, inputdir=Path(inputdir), output_path=Path(inputdir) / "ocn"
    )
    return SimpleNamespace(cesmroot=Path("/cesm"), workflow_context=lambda: ctx)


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
        inputdir=tmp_path,
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
                "outputs": {
                    "ROF2OCN_LIQ_RMAPNAME": "map.nc",
                    "ROF2OCN_ICE_RMAPNAME": "map.nc",
                },
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


# =============================================================================
# run_workflow: finished steps
# =============================================================================

_FILES_ENTRY = {
    "dummyfiles": {"name": "dummyfiles", "inputs": {"dummyfiles_x": "1"}, "outputs": {}}
}


def test_run_workflow_skips_a_finished_step(tmp_path):
    _DummyFilesConfigurator.existed.clear()
    case = _case(_FILES_ENTRY, inputdir=tmp_path)

    run_workflow(case, dummyfiles=True)
    run_workflow(case, dummyfiles=True)

    assert _DummyFilesConfigurator.existed == [False]


def test_run_workflow_force_reruns_after_removing_old_files(tmp_path):
    _DummyFilesConfigurator.existed.clear()
    case = _case(_FILES_ENTRY, inputdir=tmp_path)

    run_workflow(case, dummyfiles=True)
    run_workflow(case, force=True, dummyfiles=True)

    # The engines keep a file that already exists, so a rerun must not find it.
    assert _DummyFilesConfigurator.existed == [False, False]


def test_portable_settings_equal_across_inputdirs(tmp_path):
    def settings(inputdir, cesmroot):
        x = [str(inputdir / "ocn" / "x.nc"), str(cesmroot / "cime")]
        config = {"dummyfiles": {"name": "dummyfiles", "inputs": {"dummyfiles_x": x}}}
        return portable_settings(_DummyFilesConfigurator, config, inputdir, cesmroot)

    a = settings(tmp_path / "a", tmp_path / "cesm_a")

    assert a == settings(tmp_path / "b", tmp_path / "cesm_b")
    assert a["dummyfiles"]["inputs"]["dummyfiles_x"] == [
        "$INPUTDIR/ocn/x.nc",
        "$CESMROOT/cime",
    ]
