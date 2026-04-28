import pytest
from unittest.mock import Mock, MagicMock, patch
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


# =============================================================================
# Tests for individual process_* wrapper functions
# =============================================================================


def _make_mock_config(config_dict=None, inputdir=None, ocn_grid=None, ocn_topo=None):
    """Build a MagicMock that behaves like utils.Config for the driver module."""
    cfg = MagicMock()
    cfg.config = config_dict or {}
    cfg.__getitem__.side_effect = lambda k: cfg.config[k]
    cfg.inputdir = inputdir or Path("/tmp/cfg_inputdir")
    cfg.ocn_grid = ocn_grid or MagicMock(nx=10, ny=12)
    cfg.ocn_topo = ocn_topo or MagicMock()
    return cfg


@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_test_driver_prints(mock_Config, capsys):
    """test_driver() should load config and print confirmation lines."""
    mock_Config.return_value = _make_mock_config()
    driver.test_driver()
    captured = capsys.readouterr()
    assert "All Imports Work!" in captured.out
    assert "Config Loads!" in captured.out


@patch("CrocoDash.extract_forcings.case_setup.driver.bgc.process_bgc_ic")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_bgcic_invokes_bgc(mock_Config, mock_bgc_ic, tmp_path):
    mock_Config.return_value = _make_mock_config(
        config_dict={
            "bgcic": {
                "inputs": {"marbl_ic_filepath": "/some/path.nc"},
                "outputs": {"MARBL_TRACERS_IC_FILE": "tracers_ic.nc"},
            }
        },
        inputdir=tmp_path,
    )
    driver.process_bgcic()
    mock_bgc_ic.assert_called_once()
    _, kwargs = mock_bgc_ic.call_args
    assert kwargs["file_path"] == "/some/path.nc"
    assert kwargs["output_path"] == tmp_path / "ocnice" / "tracers_ic.nc"


@patch("CrocoDash.extract_forcings.case_setup.driver.bgc.process_bgc_iron_forcing")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_bgcironforcing_invokes_bgc(mock_Config, mock_iron, tmp_path):
    mock_Config.return_value = _make_mock_config(
        config_dict={
            "bgcironforcing": {
                "outputs": {
                    "MARBL_FESEDFLUX_FILE": "fesed.nc",
                    "MARBL_FEVENTFLUX_FILE": "fevent.nc",
                }
            }
        },
        inputdir=tmp_path,
    )
    driver.process_bgcironforcing()
    mock_iron.assert_called_once()
    _, kwargs = mock_iron.call_args
    assert kwargs["nx"] == 10
    assert kwargs["ny"] == 12
    assert kwargs["MARBL_FESEDFLUX_FILE"] == "fesed.nc"
    assert kwargs["MARBL_FEVENTFLUX_FILE"] == "fevent.nc"
    assert kwargs["inputdir"] == tmp_path


@patch("CrocoDash.extract_forcings.case_setup.driver.rof.generate_rof_ocn_map")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_runoff_invokes_rof(mock_Config, mock_rof, tmp_path):
    mock_Config.return_value = _make_mock_config(
        config_dict={
            "runoff": {
                "inputs": {
                    "rof_grid_name": "GLOFAS",
                    "rof_esmf_mesh_filepath": "/rof/mesh.nc",
                    "case_esmf_mesh_path": "/case/mesh.nc",
                    "case_grid_name": "panama1",
                    "rmax": 20,
                    "fold": 40,
                }
            }
        },
        inputdir=tmp_path,
    )
    driver.process_runoff()
    mock_rof.assert_called_once()
    _, kwargs = mock_rof.call_args
    assert kwargs["rof_grid_name"] == "GLOFAS"
    assert kwargs["rmax"] == 20
    assert kwargs["fold"] == 40


@patch("CrocoDash.extract_forcings.case_setup.driver.bgc.process_river_nutrients")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_bgcrivernutrients_invokes_bgc(mock_Config, mock_rn, tmp_path):
    mock_Config.return_value = _make_mock_config(
        config_dict={
            "bgcrivernutrients": {
                "inputs": {"global_river_nutrients_filepath": "/rn.nc"},
                "outputs": {"RIV_FLUX_FILE": "riv_flux.nc"},
            },
            "runoff": {"outputs": {"ROF2OCN_LIQ_RMAPNAME": "/map.nc"}},
        },
        inputdir=tmp_path,
    )
    driver.process_bgcrivernutrients()
    mock_rn.assert_called_once()
    _, kwargs = mock_rn.call_args
    assert kwargs["global_river_nutrients_filepath"] == "/rn.nc"
    assert kwargs["mapping_file"] == "/map.nc"
    assert (
        kwargs["river_nutrients_nnsm_filepath"] == tmp_path / "ocnice" / "riv_flux.nc"
    )


@patch("CrocoDash.extract_forcings.case_setup.driver.tides.process_tides")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_tides_invokes_tides(mock_Config, mock_tides, tmp_path):
    mock_Config.return_value = _make_mock_config(
        config_dict={
            "basic": {
                "paths": {
                    "hgrid_path": "/hgrid.nc",
                    "vgrid_path": "/vgrid.nc",
                }
            },
            "tides": {
                "inputs": {
                    "tidal_constituents": ["M2"],
                    "boundaries": ["east"],
                    "tpxo_elevation_filepath": "/elev.nc",
                    "tpxo_velocity_filepath": "/vel.nc",
                }
            },
        },
        inputdir=tmp_path,
    )
    driver.process_tides()
    mock_tides.assert_called_once()
    _, kwargs = mock_tides.call_args
    assert kwargs["tidal_constituents"] == ["M2"]
    assert kwargs["boundaries"] == ["east"]


@patch("CrocoDash.extract_forcings.case_setup.driver.chl.process_chl")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_chl_invokes_chl(mock_Config, mock_chl, tmp_path):
    mock_Config.return_value = _make_mock_config(
        config_dict={
            "chl": {
                "inputs": {"chl_processed_filepath": "/chl_raw.nc"},
                "outputs": {"CHL_FILE": "/chl_out.nc"},
            }
        },
        inputdir=tmp_path,
    )
    driver.process_chl()
    mock_chl.assert_called_once()
    _, kwargs = mock_chl.call_args
    assert kwargs["chl_processed_filepath"] == "/chl_raw.nc"
    assert kwargs["output_filepath"] == "/chl_out.nc"


# process_conditions internally calls utils.Config + gdp, rdp, mpd.
@patch("CrocoDash.extract_forcings.case_setup.driver.mpd.merge_piecewise_dataset")
@patch("CrocoDash.extract_forcings.case_setup.driver.rdp.regrid_dataset_piecewise")
@patch("CrocoDash.extract_forcings.case_setup.driver.gdp.get_dataset_piecewise")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_conditions_calls_all_three_stages(
    mock_Config, mock_gdp, mock_rdp, mock_mpd
):
    base_cfg = {
        "basic": {
            "forcing": {
                "product_name": "GLORYS",
                "function_name": "download",
                "information": {},
            },
            "dates": {"format": "%Y%m%d", "start": "20200101", "end": "20200106"},
            "paths": {
                "hgrid_path": "/h.nc",
                "bathymetry_path": "/b.nc",
                "raw_dataset_path": "/raw",
                "regridded_dataset_path": "/regrid",
                "output_path": "/out",
                "vgrid_path": "/v.nc",
            },
            "general": {
                "step": "5",
                "boundary_number_conversion": {"east": 1},
                "preview": True,
            },
            "file_regex": {
                "raw_dataset_pattern": "pat1",
                "regridded_dataset_pattern": "pat2",
            },
        }
    }
    mock_Config.return_value = _make_mock_config(config_dict=base_cfg)
    driver.process_conditions(
        get_dataset_piecewise=True,
        regrid_dataset_piecewise=True,
        merge_piecewise_dataset=True,
    )
    mock_gdp.assert_called_once()
    mock_rdp.assert_called_once()
    mock_mpd.assert_called_once()


@patch("CrocoDash.extract_forcings.case_setup.driver.mpd.merge_piecewise_dataset")
@patch("CrocoDash.extract_forcings.case_setup.driver.rdp.regrid_dataset_piecewise")
@patch("CrocoDash.extract_forcings.case_setup.driver.gdp.get_dataset_piecewise")
@patch("CrocoDash.extract_forcings.case_setup.driver.utils.Config")
def test_process_conditions_respects_skip_flags(
    mock_Config, mock_gdp, mock_rdp, mock_mpd
):
    """When all three stages are disabled, none of the three submodules is called."""
    mock_Config.return_value = _make_mock_config(config_dict={"basic": {}})
    driver.process_conditions(
        get_dataset_piecewise=False,
        regrid_dataset_piecewise=False,
        merge_piecewise_dataset=False,
    )
    mock_gdp.assert_not_called()
    mock_rdp.assert_not_called()
    mock_mpd.assert_not_called()


# =============================================================================
# Tests for run_from_cli branch dispatch
# =============================================================================


def _full_args(**overrides):
    """Build a Namespace with every attribute run_from_cli expects, defaulting to False."""
    defaults = dict(
        all=False,
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
    defaults.update(overrides)
    return Namespace(**defaults)


@patch("CrocoDash.extract_forcings.case_setup.driver.test_driver")
def test_run_from_cli_test_flag_short_circuits(mock_test_driver):
    """--test should call test_driver and exit early without touching any components."""
    args = _full_args(test=True, all=True)  # 'all' should be ignored
    cfg = Mock()
    cfg.config = {"tides": {}, "runoff": {}}

    driver.run_from_cli(args, cfg)
    mock_test_driver.assert_called_once()


@patch("CrocoDash.extract_forcings.case_setup.driver.process_chl")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_tides")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_bgcrivernutrients")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_runoff")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_bgcironforcing")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_bgcic")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_conditions")
def test_run_from_cli_dispatches_each_component(
    mock_conditions,
    mock_bgcic,
    mock_iron,
    mock_runoff,
    mock_rn,
    mock_tides,
    mock_chl,
):
    """With --all and every component in config, each process_* is called exactly once."""
    args = _full_args(all=True)
    cfg = Mock()
    cfg.config = {
        "bgcic": {},
        "bgcironforcing": {},
        "runoff": {},
        "bgcrivernutrients": {},
        "tides": {},
        "chl": {},
    }

    driver.run_from_cli(args, cfg)

    # --all also enables ic/bc (they are treated as always-present in config).
    mock_conditions.assert_called_once()
    mock_bgcic.assert_called_once()
    mock_iron.assert_called_once()
    mock_runoff.assert_called_once()
    mock_rn.assert_called_once()
    mock_tides.assert_called_once()
    mock_chl.assert_called_once()


@patch("CrocoDash.extract_forcings.case_setup.driver.process_chl")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_tides")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_bgcrivernutrients")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_runoff")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_bgcironforcing")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_bgcic")
@patch("CrocoDash.extract_forcings.case_setup.driver.process_conditions")
def test_run_from_cli_ic_flag_calls_conditions(
    mock_conditions,
    mock_bgcic,
    mock_iron,
    mock_runoff,
    mock_rn,
    mock_tides,
    mock_chl,
):
    """--ic triggers process_conditions with run_initial_condition=True."""
    args = _full_args(ic=True, no_get=True)
    cfg = Mock()
    cfg.config = {}
    driver.run_from_cli(args, cfg)
    mock_conditions.assert_called_once()
    _, kwargs = mock_conditions.call_args
    assert kwargs["run_initial_condition"] is True
    assert kwargs["run_boundary_conditions"] is False
    assert kwargs["get_dataset_piecewise"] is False  # --no-get was set
    # None of the component-level processes should run.
    for m in (mock_bgcic, mock_iron, mock_runoff, mock_rn, mock_tides, mock_chl):
        m.assert_not_called()
