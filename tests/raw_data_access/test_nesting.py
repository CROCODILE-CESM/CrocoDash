from CrocoDash.raw_data_access.datasets import nesting as ns
from CrocoDash.raw_data_access.datasets.nesting import _build_diag_table_entries
from CrocoDash.raw_data_access.registry import ProductRegistry
import xarray as xr
import numpy as np
import pandas as pd
import pytest

SAMPLE_SLICES = [
    {
        "name": "Florida_Cuba",
        "lon_min": -80.529,
        "lon_max": -80.529,
        "lat_min": 22.894,
        "lat_max": 25.223,
    },
    {
        "name": "Florida_Strait",
        "lon_min": -80.115,
        "lon_max": -78.869,
        "lat_min": 26.636,
        "lat_max": 26.636,
    },
]
CASE_PREFIX = "test_case.mom6"
DATES = ["2020-01-01", "2020-03-31"]
BUFFER = ns.NESTING.BUFFER_DEG


# --- Registration ---


def test_product_registered():
    ProductRegistry.load()
    assert ProductRegistry.product_exists("nesting")
    assert "get_nesting_slices" in ProductRegistry.list_access_methods("nesting")


def test_forcing_product_metadata():
    assert ns.NESTING.tracer_var_names == {"temp": "thetao", "salt": "so"}
    assert ns.NESTING.u_var_name == "uo"
    assert ns.NESTING.v_var_name == "vo"
    assert ns.NESTING.eta_var_name == "zos"


# --- Diag table generation ---


def test_diag_table_contains_all_slices():
    text = _build_diag_table_entries(SAMPLE_SLICES, CASE_PREFIX)
    for s in SAMPLE_SLICES:
        assert s["name"] in text


def test_diag_table_buffer_applied():
    text = _build_diag_table_entries(SAMPLE_SLICES, CASE_PREFIX, buffer_deg=0.5)
    # Florida_Cuba: lon buffered from -80.529±0.5, lat buffered from 22.894-0.5 to 25.223+0.5
    assert "-81.029" in text
    assert "-80.029" in text
    assert "22.394" in text
    assert "25.723" in text


def test_diag_table_all_variables():
    text = _build_diag_table_entries(SAMPLE_SLICES, CASE_PREFIX)
    for var in ns.NESTING.SLICE_VARIABLES:
        assert var in text


def test_diag_table_file_section_format():
    text = _build_diag_table_entries([SAMPLE_SLICES[0]], CASE_PREFIX)
    assert f'"{CASE_PREFIX}.Florida_Cuba%4yr-%2mo"' in text
    assert '"ocean_model_z"' in text
    assert '"all", "mean"' in text


def test_diag_table_vert_bounds():
    text = _build_diag_table_entries(SAMPLE_SLICES, CASE_PREFIX)
    assert "-1 -1" in text


# --- Missing files path ---


def test_missing_output_dir_returns_none_and_prints(tmp_path, capsys):
    result = ns.NESTING.get_nesting_slices(
        dates=DATES,
        output_dir=tmp_path,  # empty dir — no files
        case_prefix=CASE_PREFIX,
        slices=SAMPLE_SLICES,
        output_folder=tmp_path,
    )
    assert result is None
    captured = capsys.readouterr()
    assert "diag_table" in captured.out
    assert "Florida_Cuba" in captured.out


def test_none_output_dir_returns_none(tmp_path, capsys):
    result = ns.NESTING.get_nesting_slices(
        dates=DATES,
        output_dir=None,
        case_prefix=CASE_PREFIX,
        slices=SAMPLE_SLICES,
        output_folder=tmp_path,
    )
    assert result is None


def test_empty_slices_returns_none(tmp_path):
    result = ns.NESTING.get_nesting_slices(
        dates=DATES,
        output_dir=tmp_path,
        case_prefix=CASE_PREFIX,
        slices=[],
        output_folder=tmp_path,
    )
    assert result is None


# --- Date coverage check ---


def _write_mock_slice(output_dir, case_prefix, slice_name, times):
    """Write a minimal mock slice NetCDF file."""
    ds = xr.Dataset(
        {
            "thetao": (["time", "z_l", "xh", "yh"], np.ones((len(times), 2, 3, 3))),
        },
        coords={
            "time": times,
            "z_l": [5.0, 50.0],
            "xh": [0.0, 1.0, 2.0],
            "yh": [0.0, 1.0, 2.0],
        },
    )
    path = output_dir / f"{case_prefix}.{slice_name}_mock.nc"
    ds.to_netcdf(path)
    return path


def test_date_coverage_check_fails_when_data_too_short(tmp_path):
    times = pd.date_range("2020-01-01", "2020-01-31", freq="D")
    for s in SAMPLE_SLICES:
        _write_mock_slice(tmp_path, CASE_PREFIX, s["name"], times)

    result = ns.NESTING.get_nesting_slices(
        dates=["2020-01-01", "2020-06-30"],  # requests beyond available data
        output_dir=tmp_path,
        case_prefix=CASE_PREFIX,
        slices=SAMPLE_SLICES,
        output_folder=tmp_path,
    )
    assert result is None


def test_loads_and_saves_when_coverage_ok(tmp_path):
    times = pd.date_range("2020-01-01", "2020-04-30", freq="D")
    for s in SAMPLE_SLICES:
        _write_mock_slice(tmp_path, CASE_PREFIX, s["name"], times)

    result = ns.NESTING.get_nesting_slices(
        dates=DATES,
        output_dir=tmp_path,
        case_prefix=CASE_PREFIX,
        slices=SAMPLE_SLICES,
        output_folder=tmp_path,
        output_filename="out.nc",
    )
    assert result is not None
    assert result.exists()
    # verify groups are present
    ds_check = xr.open_dataset(result, group="Florida_Cuba")
    assert "thetao" in ds_check
