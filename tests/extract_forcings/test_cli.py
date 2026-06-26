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
            "dates": {"start": "20200101", "end": "20200109", "format": "%Y%m%d"},
            "forcing": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_from_rda",
                "information": {},
            },
            "general": {
                "boundary_number_conversion": {"north": 1},
                "step": "7",
                "preview": False,
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
def test_process_missing_config_raises_helpful_error(mock_read, tmp_path):
    """Clear error when configure_forcings hasn't been run yet."""
    caseroot = tmp_path / "mycase"
    caseroot.mkdir()
    inputdir = tmp_path / "input"
    inputdir.mkdir()
    # extract_forcings/ dir does NOT exist — configure_forcings never ran

    mock_read.return_value = {"inputdir": str(inputdir)}

    with pytest.raises(FileNotFoundError, match="configure_forcings"):
        run_main(["process", "--caseroot", str(caseroot), "--all"])


# =============================================================================
# _process integration (mock run_workflow)
# =============================================================================


@patch("CrocoDash.extract_forcings.driver.run_workflow")
@patch("CrocoDash.extract_forcings.driver.resolve_components")
def test_process_config_flag(mock_resolve, mock_run, tmp_path):
    """--config takes a direct path to config.json, skipping case_state lookup."""
    config_path = tmp_path / "config.json"
    _write_config(config_path)
    mock_resolve.side_effect = lambda args, cfg: args

    run_main(["process", "--config", str(config_path), "--all"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["config_path"] == config_path


@patch("CrocoDash.extract_forcings.driver.run_workflow")
@patch("CrocoDash.extract_forcings.driver.resolve_components")
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


@patch("CrocoDash.extract_forcings.driver.run_workflow")
@patch("CrocoDash.extract_forcings.driver.resolve_components")
def test_process_auto_detect_config_in_cwd(
    mock_resolve, mock_run, tmp_path, monkeypatch
):
    """If cwd contains config.json, use it without --caseroot."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "config.json")
    mock_resolve.side_effect = lambda args, cfg: args

    run_main(["process", "--all"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["config_path"] == tmp_path / "config.json"


@patch("CrocoDash.extract_forcings.driver.run_workflow")
@patch("CrocoDash.extract_forcings.driver.resolve_components")
@patch("CrocoDash.case_state.read")
def test_process_defaults_to_cwd_as_caseroot(
    mock_read, mock_resolve, mock_run, tmp_path, monkeypatch
):
    """Without --caseroot and without config.json in cwd, treats cwd as caseroot."""
    monkeypatch.chdir(tmp_path)
    inputdir = tmp_path / "input"
    inputdir.mkdir()
    ef_dir = inputdir / "extract_forcings"
    ef_dir.mkdir()
    _write_config(ef_dir / "config.json")

    mock_read.return_value = {"inputdir": str(inputdir)}
    mock_resolve.side_effect = lambda args, cfg: args

    run_main(["process", "--ic"])

    mock_read.assert_called_once_with(tmp_path)
    assert mock_run.called


@patch("CrocoDash.extract_forcings.driver.run_workflow")
@patch("CrocoDash.extract_forcings.driver.resolve_components")
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
            "dates": {"start": "20200101", "end": "20200109", "format": "%Y%m%d"},
            "forcing": {
                "product_name": "GLORYS",
                "function_name": "fn",
                "information": {},
            },
            "general": {"boundary_number_conversion": {}, "step": "7", "preview": True},
        },
    }
    (ef_dir / "config.json").write_text(json.dumps(config))

    mock_read.return_value = {"inputdir": str(inputdir)}
    mock_resolve.side_effect = lambda args, cfg: args

    run_main(["process", "--caseroot", str(caseroot), "--ic"])

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["preview"] is True
