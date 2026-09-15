"""Tests for the `crocodash process` CLI subcommand."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def run_main(argv):
    with patch.object(sys, "argv", ["crocodash"] + argv):
        from CrocoDash.cli import main

        main()


def _write_config(path, extra_keys=None):
    config = {
        "caseroot": "/fake/case",
        "conditions": {
            "name": "conditions",
            "inputs": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_from_rda",
                "start_date": "20200101",
                "end_date": "20200109",
                "boundaries": ["north"],
                "compset": "MOM6",
                "function_args": {},
            },
            "outputs": {
                "date_format": "%Y%m%d",
                "information": {},
                "boundary_number_conversion": {"north": 1},
                "get_step_days": "7",
                "regrid_step_days": "7",
                "preview": False,
                "function_args": {},
            },
        },
    }
    if extra_keys:
        config.update(extra_keys)
    path.write_text(json.dumps(config))
    return config


# =============================================================================
# Basic argument parsing (via the CLI entry point)
# =============================================================================


def test_process_help():
    with pytest.raises(SystemExit) as exc:
        run_main(["process", "--help"])
    assert exc.value.code == 0


def test_process_all_args_available():
    """Verify every expected flag is registered."""
    import argparse

    with patch("CrocoDash.cli._process"):
        # This will call _process if args parse OK
        with patch.object(
            sys,
            "argv",
            [
                "crocodash",
                "process",
                "--config",
                "/some/config.json",
                "--caseroot",
                "/some/case",
                "--all",
                "--ic",
                "--bc",
                "--bgcic",
                "--bgcironforcing",
                "--bgcrivernutrients",
                "--runoff",
                "--tides",
                "--chl",
                "--skip",
                "tides",
            ],
        ):
            from CrocoDash.cli import main

            main()


# =============================================================================
# Error handling
# =============================================================================


@patch("CrocoDash.case_state.read")
def test_process_missing_config_raises_helpful_error(mock_read, tmp_path, capsys):
    """Clear error when configure_forcings hasn't been run yet."""
    caseroot = tmp_path / "mycase"
    caseroot.mkdir()
    inputdir = tmp_path / "input"
    inputdir.mkdir()
    # extract_forcings/ dir does NOT exist — configure_forcings never ran

    mock_read.return_value = {"inputdir": str(inputdir)}

    with pytest.raises(SystemExit) as exc_info:
        run_main(["process", "--caseroot", str(caseroot), "--all"])
    assert exc_info.value.code == 1
    assert "configure_forcings" in capsys.readouterr().err


# =============================================================================
# _process integration (mock run_workflow)
# =============================================================================


@patch("CrocoDash.forcing.driver.run_workflow")
def test_process_config_flag(mock_run, tmp_path):
    """--config takes a direct path to config.json, skipping case_state lookup."""
    config_path = tmp_path / "config.json"
    _write_config(config_path)

    run_main(["process", "--config", str(config_path), "--all"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["config_path"] == config_path


@patch("CrocoDash.forcing.driver.run_workflow")
@patch("CrocoDash.forcing.driver.resolve_components")
@patch("CrocoDash.case_state.read")
def test_process_caseroot_flag(mock_read, mock_resolve, mock_run, tmp_path):
    caseroot = tmp_path / "mycase"
    caseroot.mkdir()
    inputdir = tmp_path / "input"
    inputdir.mkdir()
    ef_dir = inputdir / "extract_forcings"
    ef_dir.mkdir()
    _write_config(ef_dir / "config.json")

    mock_read.return_value = {"inputdir": str(inputdir)}
    mock_resolve.side_effect = lambda args, cfg: args  # pass-through

    run_main(["process", "--caseroot", str(caseroot), "--ic"])

    mock_read.assert_called_once_with(caseroot)
    assert mock_run.called


@patch("CrocoDash.forcing.driver.run_workflow")
def test_process_auto_detect_config_in_cwd(mock_run, tmp_path, monkeypatch):
    """If cwd contains config.json, use it without --caseroot."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "config.json")

    run_main(["process", "--all"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["config_path"] == tmp_path / "config.json"


def test_process_no_config_in_cwd_raises_helpful_error(tmp_path, monkeypatch, capsys):
    """Without --caseroot and without config.json in cwd, shows a clear error."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        run_main(["process", "--ic"])
    assert exc_info.value.code == 1
    assert "--caseroot" in capsys.readouterr().err


@patch("CrocoDash.forcing.driver.run_workflow")
@patch("CrocoDash.forcing.driver.resolve_components")
@patch("CrocoDash.case_state.read")
def test_process_preview_from_config(mock_read, mock_resolve, mock_run, tmp_path):
    caseroot = tmp_path / "mycase"
    caseroot.mkdir()
    inputdir = tmp_path / "input"
    inputdir.mkdir()
    ef_dir = inputdir / "extract_forcings"
    ef_dir.mkdir()

    config = {
        "caseroot": str(caseroot),
        "conditions": {
            "inputs": {
                "product_name": "GLORYS",
                "function_name": "fn",
                "start_date": "20200101",
                "end_date": "20200109",
            },
            "outputs": {
                "date_format": "%Y%m%d",
                "information": {},
                "boundary_number_conversion": {},
                "get_step_days": "7",
                "regrid_step_days": "7",
                "preview": True,
            },
        },
    }
    (ef_dir / "config.json").write_text(json.dumps(config))

    mock_read.return_value = {"inputdir": str(inputdir)}
    mock_resolve.side_effect = lambda args, cfg: args

    run_main(["process", "--caseroot", str(caseroot), "--ic"])

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["preview"] is True
