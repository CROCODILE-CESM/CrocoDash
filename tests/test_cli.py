"""CLI-level tests for the `crocodash` entry point.

These stop at argument parsing and dispatch -- what flags exist, and what the
handler forwards -- and stub out the work itself. The behaviour behind each flag
is covered by tests/test_recipe_functions.py.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import CrocoDash.cli as cli
import CrocoDash.recipe as recipe
from CrocoDash.case import Case


@pytest.fixture
def captured_create(monkeypatch):
    """Run `crocodash create` without creating anything.

    _create imports load_config/create_case_from_yaml from CrocoDash.recipe at
    call time, so patching them on the module is enough -- no import-order
    juggling needed.
    """
    calls = {}

    monkeypatch.setattr(recipe, "load_config", lambda path: {"path": path})

    def fake_create(config, override=False, configure_only=False):
        calls.update(config=config, override=override, configure_only=configure_only)

    monkeypatch.setattr(recipe, "create_case_from_yaml", fake_create)

    def run(*argv):
        monkeypatch.setattr("sys.argv", ["crocodash", "create", *argv])
        cli.main()
        return calls

    return run


def test_create_configure_only_defaults_off(captured_create):
    """Omitting the flag must keep the full create+process behaviour."""
    calls = captured_create("--config", "case.yaml")
    assert calls["configure_only"] is False


def test_create_configure_only_flag(captured_create):
    """--configure-only stops after configure_forcings.

    Needed by callers that stage their own input data between configuring a
    case and extracting its forcing -- crocontainer's regional test suite drives
    exactly this split (`crocodash create --configure-only`, stage, then
    `crocodash process`).
    """
    calls = captured_create("--config", "case.yaml", "--configure-only")
    assert calls["configure_only"] is True


def test_create_forwards_override(captured_create):
    """The flag must not disturb the argument that was already there."""
    calls = captured_create("--config", "case.yaml", "--override")
    assert calls["override"] is True
    assert calls["configure_only"] is False


def test_bundle_cli(monkeypatch, tmp_path):
    case = MagicMock()
    case.name = "case"
    monkeypatch.setattr(Case, "from_caseroot", MagicMock(return_value=case))
    monkeypatch.setattr(
        "sys.argv",
        ["crocodash", "bundle", "--caseroot", "/some/case"]
        + ["--output-dir", str(tmp_path), "--machine", "derecho"],
    )
    cli.main()

    Case.from_caseroot.assert_called_once_with("/some/case")
    case.bundle.assert_called_once_with(tmp_path / "case_case_bundle")


_COMPSET = "1850_DATM%NYF_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV"

# A configured case, as Case.from_caseroot() reads it, without CIME.
_SOURCE = SimpleNamespace(
    caseroot=Path("/src/case"),
    inputdir=Path("/src/input"),
    cesmroot=Path("/src/cesm"),
    machine="derecho",
    project="P1",
    compset_lname=_COMPSET,
    bundled_from=None,
    _configure_forcings_called=True,
    forcing_config={
        "conditions": {
            "inputs": {
                "start_date": "20200101",
                "end_date": "20200109",
                "boundaries": ["north"],
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_from_rda",
                "function_args": {"buf": 2.0},
            }
        }
    },
    forcing_args=lambda: {
        "date_range": ["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        "boundaries": ["north"],
        "product_name": "GLORYS",
        "function_name": "get_glorys_data_from_rda",
        "function_overrides": {"buf": 2.0},
    },
)


def _fork(monkeypatch, *argv):
    """Run `crocodash fork` on _SOURCE; the call it makes to Case.fork, or
    None."""
    fork = MagicMock()
    monkeypatch.setattr(Case, "from_caseroot", lambda path: _SOURCE)
    monkeypatch.setattr(Case, "fork", fork)
    monkeypatch.setattr("sys.argv", ["crocodash", "fork", *argv])
    cli.main()
    return fork.call_args


def test_fork_forwards_the_new_case_flags(monkeypatch, tmp_path):
    forked = _fork(
        monkeypatch,
        *["--bundle", "/some/bundle", "--caseroot", str(tmp_path / "case")],
        *["--inputdir", str(tmp_path / "input"), "--cesmroot", "/some/cesm"],
        *["--machine", "casper", "--project", "PROJ123", "--no-input"],
        *["--plan", json.dumps({"user_nl": False, "forcing_files": "none"})],
    )

    assert forked == call(
        _SOURCE,
        str(tmp_path / "case"),
        str(tmp_path / "input"),
        cesmroot="/some/cesm",
        machine="casper",
        project="PROJ123",
        compset=_COMPSET,
        changes={},
        plan={
            "xmlchanges": True,
            "user_nl": False,
            "source_mods": True,
            "xml_files": True,
            "forcing_files": "none",
        },
    )


def test_fork_yaml_round_trips_unchanged(monkeypatch, tmp_path):
    """--write-yaml, then --config with that file, forks as --no-input does:
    the YAML changes nothing on its way through."""
    yaml_file = str(tmp_path / "fork.yaml")
    new_case = ["--source", "/src/case", "--caseroot", str(tmp_path / "case")]
    new_case += ["--inputdir", str(tmp_path / "input")]

    no_input = _fork(monkeypatch, *new_case, "--no-input")
    assert _fork(monkeypatch, *new_case, "--write-yaml", yaml_file) is None
    assert _fork(monkeypatch, "--config", yaml_file) == no_input
    assert no_input.kwargs["changes"] == {}


def test_fork_prompts_keep_the_defaults_after_end_of_input(monkeypatch, tmp_path):
    """Input that ends early (Ctrl-D, or a short script) keeps the default of
    every prompt left: here all but the first, the caseroot."""
    answers = iter([str(tmp_path / "typed")])

    def type_answer(prompt):
        answer = next(answers, None)
        if answer is None:
            raise EOFError
        return answer

    monkeypatch.setattr("builtins.input", type_answer)
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    source = ["--source", "/src/case", "--inputdir", str(tmp_path / "input")]

    prompted = _fork(monkeypatch, *source, "--caseroot", str(tmp_path / "flag"))
    assert prompted == _fork(
        monkeypatch, *source, "--caseroot", str(tmp_path / "typed"), "--no-input"
    )
