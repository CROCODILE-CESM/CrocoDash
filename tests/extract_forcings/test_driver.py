import pytest
from unittest.mock import DEFAULT, Mock, MagicMock, patch
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


@pytest.mark.parametrize(
    "argv,expected",
    [
        pytest.param(
            ["driver.py", "--all"],
            {"all": True, "skip": []},
            id="all_flag_and_default_skip",
        ),
        pytest.param(
            ["driver.py", "--ic"],
            {"ic": True, "bc": False},
            id="single_component_flag",
        ),
        pytest.param(
            ["driver.py", "--bgcic", "--tides", "--runoff"],
            {"bgcic": True, "tides": True, "runoff": True, "chl": False},
            id="multiple_component_flags",
        ),
        pytest.param(
            ["driver.py", "--all", "--skip", "tides"],
            {"skip": ["tides"]},
            id="skip_single",
        ),
    ],
)
def test_parse_args_flags(argv, expected):
    """parse_args correctly parses supported flag combinations."""
    with patch.object(sys, "argv", argv):
        args = driver.parse_args()
    for key, val in expected.items():
        assert (
            getattr(args, key) == val
        ), f"expected {key}={val}, got {getattr(args, key)}"


def test_parse_args_no_args_exits():
    """No arguments -> help printed and SystemExit."""
    with patch.object(sys, "argv", ["driver.py"]):
        with pytest.raises(SystemExit):
            driver.parse_args()


def _args_ns(**overrides):
    """Build a Namespace with every flag resolve_components/run_from_cli expects."""
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


@pytest.mark.parametrize(
    "arg_overrides,config_keys,expected",
    [
        pytest.param(
            {"all": True},
            ["tides", "runoff", "bgcic"],
            {"tides": True, "runoff": True, "bgcic": True, "chl": False},
            id="all_flag_enables_all_in_config",
        ),
        pytest.param(
            {"all": True, "skip": ["TIDES", "Runoff"]},
            ["tides", "runoff", "bgcic"],
            {"tides": False, "runoff": False, "bgcic": True},
            id="skip_is_case_insensitive",
        ),
        pytest.param(
            {"bgcic": True, "runoff": True},
            ["bgcic"],  # runoff missing from config
            {"bgcic": True, "runoff": False},
            id="requested_but_missing_in_config_disabled",
        ),
        pytest.param(
            {"bgcic": True, "tides": True},
            ["bgcic", "tides", "runoff"],
            {"bgcic": True, "tides": True, "runoff": False},
            id="individual_flags_without_all",
        ),
    ],
)
def test_resolve_components(arg_overrides, config_keys, expected):
    """resolve_components honors --all, --skip, and individual component flags."""
    args = _args_ns(**arg_overrides)
    config = Mock()
    config.config = {k: {} for k in config_keys}

    resolved = driver.resolve_components(args, config)

    for comp, want in expected.items():
        assert (
            getattr(resolved, comp) is want
        ), f"{comp}: expected {want}, got {getattr(resolved, comp)}"


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


@pytest.mark.parametrize(
    "driver_fn_name,underlying_patch,config_dict,kwarg_checks",
    [
        pytest.param(
            "process_bgcic",
            "CrocoDash.extract_forcings.case_setup.driver.bgc.process_bgc_ic",
            {
                "bgcic": {
                    "inputs": {"marbl_ic_filepath": "/some/path.nc"},
                    "outputs": {"MARBL_TRACERS_IC_FILE": "tracers_ic.nc"},
                }
            },
            lambda kw, tmp_path: (
                kw["file_path"] == "/some/path.nc"
                and kw["output_path"] == tmp_path / "ocnice" / "tracers_ic.nc"
            ),
            id="bgcic",
        ),
        pytest.param(
            "process_bgcironforcing",
            "CrocoDash.extract_forcings.case_setup.driver.bgc.process_bgc_iron_forcing",
            {
                "bgcironforcing": {
                    "outputs": {
                        "MARBL_FESEDFLUX_FILE": "fesed.nc",
                        "MARBL_FEVENTFLUX_FILE": "fevent.nc",
                    }
                }
            },
            lambda kw, tmp_path: (
                kw["nx"] == 10
                and kw["ny"] == 12
                and kw["MARBL_FESEDFLUX_FILE"] == "fesed.nc"
                and kw["MARBL_FEVENTFLUX_FILE"] == "fevent.nc"
                and kw["inputdir"] == tmp_path
            ),
            id="bgcironforcing",
        ),
        pytest.param(
            "process_runoff",
            "CrocoDash.extract_forcings.case_setup.driver.rof.generate_rof_ocn_map",
            {
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
            lambda kw, tmp_path: (
                kw["rof_grid_name"] == "GLOFAS"
                and kw["rmax"] == 20
                and kw["fold"] == 40
            ),
            id="runoff",
        ),
        pytest.param(
            "process_bgcrivernutrients",
            "CrocoDash.extract_forcings.case_setup.driver.bgc.process_river_nutrients",
            {
                "bgcrivernutrients": {
                    "inputs": {"global_river_nutrients_filepath": "/rn.nc"},
                    "outputs": {"RIV_FLUX_FILE": "riv_flux.nc"},
                },
                "runoff": {"outputs": {"ROF2OCN_LIQ_RMAPNAME": "/map.nc"}},
            },
            lambda kw, tmp_path: (
                kw["global_river_nutrients_filepath"] == "/rn.nc"
                and kw["mapping_file"] == "/map.nc"
                and kw["river_nutrients_nnsm_filepath"]
                == tmp_path / "ocnice" / "riv_flux.nc"
            ),
            id="bgcrivernutrients",
        ),
        pytest.param(
            "process_tides",
            "CrocoDash.extract_forcings.case_setup.driver.tides.process_tides",
            {
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
            lambda kw, tmp_path: (
                kw["tidal_constituents"] == ["M2"] and kw["boundaries"] == ["east"]
            ),
            id="tides",
        ),
        pytest.param(
            "process_chl",
            "CrocoDash.extract_forcings.case_setup.driver.chl.process_chl",
            {
                "chl": {
                    "inputs": {"chl_processed_filepath": "/chl_raw.nc"},
                    "outputs": {"CHL_FILE": "/chl_out.nc"},
                }
            },
            lambda kw, tmp_path: (
                kw["chl_processed_filepath"] == "/chl_raw.nc"
                and kw["output_filepath"] == "/chl_out.nc"
            ),
            id="chl",
        ),
    ],
)
def test_process_wrapper_invokes_underlying(
    driver_fn_name, underlying_patch, config_dict, kwarg_checks, tmp_path
):
    """Each driver.process_* wrapper loads Config and forwards kwargs to its underlying function."""
    with patch(
        "CrocoDash.extract_forcings.case_setup.driver.utils.Config"
    ) as mock_Config, patch(underlying_patch) as mock_underlying:
        mock_Config.return_value = _make_mock_config(
            config_dict=config_dict, inputdir=tmp_path
        )
        getattr(driver, driver_fn_name)()

    mock_underlying.assert_called_once()
    _, kwargs = mock_underlying.call_args
    assert kwarg_checks(kwargs, tmp_path), f"kwargs failed expectations: {kwargs}"


_FULL_CONDITIONS_CFG = {
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


@pytest.mark.parametrize(
    "stage_flags,expect_called",
    [
        pytest.param(
            {
                "get_dataset_piecewise": True,
                "regrid_dataset_piecewise": True,
                "merge_piecewise_dataset": True,
            },
            True,
            id="all_stages_enabled",
        ),
        pytest.param(
            {
                "get_dataset_piecewise": False,
                "regrid_dataset_piecewise": False,
                "merge_piecewise_dataset": False,
            },
            False,
            id="all_stages_disabled",
        ),
    ],
)
def test_process_conditions_respects_stage_flags(stage_flags, expect_called):
    """process_conditions invokes each of gdp/rdp/mpd iff the matching flag is True."""
    with patch(
        "CrocoDash.extract_forcings.case_setup.driver.utils.Config"
    ) as mock_Config, patch(
        "CrocoDash.extract_forcings.case_setup.driver.gdp.get_dataset_piecewise"
    ) as mock_gdp, patch(
        "CrocoDash.extract_forcings.case_setup.driver.rdp.regrid_dataset_piecewise"
    ) as mock_rdp, patch(
        "CrocoDash.extract_forcings.case_setup.driver.mpd.merge_piecewise_dataset"
    ) as mock_mpd:
        mock_Config.return_value = _make_mock_config(config_dict=_FULL_CONDITIONS_CFG)
        driver.process_conditions(**stage_flags)

    for m in (mock_gdp, mock_rdp, mock_mpd):
        if expect_called:
            m.assert_called_once()
        else:
            m.assert_not_called()


# =============================================================================
# Tests for run_from_cli branch dispatch
# =============================================================================


@pytest.fixture
def mock_all_process_fns():
    """Patch every process_* function exposed on the driver module at once."""
    names = [
        "process_conditions",
        "process_bgcic",
        "process_bgcironforcing",
        "process_runoff",
        "process_bgcrivernutrients",
        "process_tides",
        "process_chl",
    ]
    with patch.multiple(
        "CrocoDash.extract_forcings.case_setup.driver",
        **{n: DEFAULT for n in names},
    ) as mocks:
        yield mocks


@patch("CrocoDash.extract_forcings.case_setup.driver.test_driver")
def test_run_from_cli_test_flag_short_circuits(mock_test_driver):
    """--test should call test_driver and exit early without touching any components."""
    args = _args_ns(test=True, all=True)  # 'all' should be ignored
    cfg = Mock()
    cfg.config = {"tides": {}, "runoff": {}}

    driver.run_from_cli(args, cfg)
    mock_test_driver.assert_called_once()


def test_run_from_cli_dispatches_each_component(mock_all_process_fns):
    """With --all and every component in config, each process_* is called exactly once."""
    args = _args_ns(all=True)
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
    for name, m in mock_all_process_fns.items():
        m.assert_called_once(), name


def test_run_from_cli_ic_flag_calls_conditions(mock_all_process_fns):
    """--ic triggers process_conditions with run_initial_condition=True; nothing else runs."""
    args = _args_ns(ic=True, no_get=True)
    cfg = Mock()
    cfg.config = {}
    driver.run_from_cli(args, cfg)

    mock_conditions = mock_all_process_fns["process_conditions"]
    mock_conditions.assert_called_once()
    _, kwargs = mock_conditions.call_args
    assert kwargs["run_initial_condition"] is True
    assert kwargs["run_boundary_conditions"] is False
    assert kwargs["get_dataset_piecewise"] is False  # --no-get was set
    for name, m in mock_all_process_fns.items():
        if name != "process_conditions":
            m.assert_not_called()
