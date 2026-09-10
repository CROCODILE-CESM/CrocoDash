"""CLI-level tests for the `crocodash` entry point.

These stop at argument parsing and dispatch -- what flags exist, and what the
handler forwards -- and stub out the work itself. The behaviour behind each flag
is covered by tests/test_recipe_functions.py.
"""

import pytest

import CrocoDash.cli as cli
import CrocoDash.recipe as recipe


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
