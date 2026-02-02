import pytest
from unittest.mock import Mock, patch
import sys
import subprocess
import json
import tempfile
from pathlib import Path
from argparse import Namespace

from CrocoDash.extract_forcings.case_setup import driver

# =============================================================================
# Argument Parsing Tests
# =============================================================================


def test_parse_args_all():
    """Test --all flag"""
    with patch.object(sys, "argv", ["driver.py", "--all"]):
        args = driver.parse_args()
        assert args.all is True


def test_parse_args_test():
    """Test --test flag"""
    with patch.object(sys, "argv", ["driver.py", "--test"]):
        args = driver.parse_args()
        assert args.test is True


def test_parse_args_with_one_on_and_others_off():
    """Test --ic (initial conditions) flag"""
    with patch.object(sys, "argv", ["driver.py", "--ic"]):
        args = driver.parse_args()
        assert args.ic is True
        assert args.bc is False


def test_parse_args_component_flags():
    """Test individual component flags"""
    with patch.object(sys, "argv", ["driver.py", "--bgcic", "--tides", "--runoff"]):
        args = driver.parse_args()
        assert args.bgcic is True
        assert args.tides is True
        assert args.runoff is True
        assert args.chl is False


def test_parse_args_skip_single():
    """Test --skip with single component"""
    with patch.object(sys, "argv", ["driver.py", "--all", "--skip", "tides"]):
        args = driver.parse_args()
        assert args.skip == ["tides"]


def test_parse_args_skip_multiple():
    """Test --skip with multiple components"""
    with patch.object(
        sys, "argv", ["driver.py", "--all", "--skip", "tides", "runoff", "bgcic"]
    ):
        args = driver.parse_args()
        assert set(args.skip) == {"tides", "runoff", "bgcic"}


def test_parse_args_skip_empty_default():
    """Test that skip defaults to empty list"""
    with patch.object(sys, "argv", ["driver.py", "--all"]):
        args = driver.parse_args()
        assert args.skip == []


def test_parse_args_no_args_exits():
    """Test that no arguments prints help and exits"""
    with patch.object(sys, "argv", ["driver.py"]):
        with pytest.raises(SystemExit):
            driver.parse_args()


# =============================================================================
# resolve_components Logic Tests (formerly should_run)
# =============================================================================


def test_resolve_components_all_flag_enables_all():
    """--all should enable all components that exist in config"""
    args = Namespace(
        all=True,
        test=False,
        no_get=False,
        no_regrid=False,
        no_merge=False,
        skip=[],
        ic=False,
        bc=False,
        bgcic=False,
        bgcironforcing=False,
        runoff=False,
        bgcrivernutrients=False,
        tides=False,
        chl=False,
    )
    config = Mock()
    config.config = {"tides": {}, "runoff": {}, "bgcic": {}}

    resolved = driver.resolve_components(args, config)

    assert resolved.tides is True
    assert resolved.runoff is True
    assert resolved.bgcic is True
    assert resolved.chl is False  # not in config


def test_resolve_components_skip_respects_case_insensitive():
    """Skip list should be case-insensitive"""
    args = Namespace(
        all=True,
        test=False,
        no_get=False,
        no_regrid=False,
        no_merge=False,
        skip=["TIDES", "Runoff"],
        ic=False,
        bc=False,
        bgcic=False,
        bgcironforcing=False,
        runoff=False,
        bgcrivernutrients=False,
        tides=False,
        chl=False,
    )
    config = Mock()
    config.config = {"tides": {}, "runoff": {}, "bgcic": {}}

    resolved = driver.resolve_components(args, config)

    assert resolved.tides is False  # skipped (case-insensitive)
    assert resolved.runoff is False  # skipped (case-insensitive)
    assert resolved.bgcic is True


def test_resolve_components_missing_in_config():
    """Components requested but not in config should be disabled"""
    args = Namespace(
        all=False,
        test=False,
        no_get=False,
        no_regrid=False,
        no_merge=False,
        skip=[],
        ic=False,
        bc=False,
        bgcic=True,
        bgcironforcing=False,
        runoff=True,
        bgcrivernutrients=False,
        tides=False,
        chl=False,
    )
    config = Mock()
    config.config = {"bgcic": {}}  # only bgcic exists

    resolved = driver.resolve_components(args, config)

    assert resolved.bgcic is True  # requested and exists
    assert resolved.runoff is False  # requested but doesn't exist


def test_resolve_components_individual_component_flag():
    """Individual component flags should work without --all"""
    args = Namespace(
        all=False,
        test=False,
        no_get=False,
        no_regrid=False,
        no_merge=False,
        skip=[],
        ic=False,
        bc=False,
        bgcic=True,
        bgcironforcing=False,
        runoff=False,
        bgcrivernutrients=False,
        tides=True,
        chl=False,
    )
    config = Mock()
    config.config = {"bgcic": {}, "tides": {}, "runoff": {}}

    resolved = driver.resolve_components(args, config)

    assert resolved.bgcic is True
    assert resolved.tides is True
    assert resolved.runoff is False  # not explicitly requested


# Some simple dry runs
@patch("CrocoDash.extract_forcings.case_setup.driver.process_runoff")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_tides")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_conditions")
def test_run_from_cli_integration(
    mock_cond, mock_tides, mock_runoff, gen_grid_topo_vgrid, tmp_path
):
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")
    topo.write_topo(tmp_path / "topo.nc")
    vgrid.write(tmp_path / "vgrid.nc")
    # Real parsing and resolution
    with patch.object(sys, "argv", ["driver.py", "--all", "--skip", "runoff"]):
        args = driver.parse_args()

    config = Mock()
    config.config = {
        "tides": {},
        "conditions": {},
        "runoff": {},
        "basic": {
            "paths": {
                "hgrid_path": tmp_path / "grid.nc",
                "topo_path": tmp_path / "topo.nc",
                "vgrid_path": tmp_path / "vgrid.nc",
            }
        },
    }

    driver.run_from_cli(args, config)  # Real execution, but process_* are mocked

    # Verify which functions were called
    assert mock_tides.called
    assert mock_cond.called
    assert mock_runoff.call_count == 0  # skipped


def test_driver_subprocess_help():
    """
    Real subprocess test: actually run driver.py --help
    Verifies the script can be invoked from command line
    """
    driver_path = (
        Path(__file__).parent.parent.parent
        / "CrocoDash"
        / "extract_forcings"
        / "case_setup"
        / "driver.py"
    )

    # Run: python driver.py --help
    result = subprocess.run(
        [sys.executable, str(driver_path), "--help"],
        capture_output=True,
        text=True,
    )

    # Should exit successfully and output help
    assert result.returncode == 0
    assert "CrocoDash forcing workflow driver" in result.stdout
    assert "--all" in result.stdout
    assert "--skip" in result.stdout
