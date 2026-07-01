from CrocoDash.raw_data_access.datasets import cesm_ocean_output as co
import xarray as xr
import pytest
import numpy as np
import cftime
import pandas as pd
from pathlib import Path
from CrocoDash.grid import Grid
from CrocoDash.raw_data_access.registry import ProductRegistry


def test_get_cesm_single_variable_data_fosi(skip_if_not_glade, tmp_path):
    dates = ["2000-01-01", "2000-01-05"]
    lat_min = 30
    lat_max = 31
    lon_min = 289
    lon_max = 290
    paths = co.CESM_OCEAN_OUTPUT.get_cesm_single_variable_data(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        tmp_path,
        "temp.nc",
        variables=["SSH"],
    )
    dataset = xr.open_dataset(paths[0])
    start = cftime.DatetimeNoLeap(2000, 1, 1, 12, 0, 0)
    end = cftime.DatetimeNoLeap(2000, 1, 5, 12, 0, 0)
    time_vals = dataset.time.values

    assert time_vals[0] <= start <= time_vals[-1], (
        f"Start date {start} not within dataset time range "
        f"({time_vals[0]} to {time_vals[-1]})"
    )
    assert time_vals[0] <= end <= time_vals[-1], (
        f"End date {end} not within dataset time range "
        f"({time_vals[0]} to {time_vals[-1]})"
    )
    assert np.abs(dataset.TLAT.values[-1, 0] - lat_max) <= 4
    assert np.abs(dataset.TLAT.values[0, 0] - lat_min) <= 4
    assert np.abs(dataset.TLONG.values[0, -1] - lon_max) <= 4
    assert np.abs(dataset.TLONG.values[0, 0] - lon_min) <= 4


def test_get_cesm_single_variable_data_lens2_member(skip_if_not_glade, tmp_path):
    dates = ["2000-01", "2000-03"]
    lat_min = 30
    lat_max = 31
    lon_min = 289
    lon_max = 290
    paths = co.CESM_OCEAN_OUTPUT.get_cesm_single_variable_data(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        tmp_path,
        variables=["SSH"],
        dataset_path="/gdex/data/d651056/CESM2-LE/ocn/proc/tseries/month_1",
        member="LE2-1001.001",
        date_format="%Y%m",
        regex=r"(\d{6})-(\d{6})",
    )
    dataset = xr.open_dataset(paths[0])

    assert np.abs(dataset.TLAT.values[-1, 0] - lat_max) <= 4
    assert np.abs(dataset.TLAT.values[0, 0] - lat_min) <= 4
    assert np.abs(dataset.TLONG.values[0, -1] - lon_max) <= 4
    assert np.abs(dataset.TLONG.values[0, 0] - lon_min) <= 4


@pytest.mark.slow
def test_get_cesm_single_variable_data_validation(skip_if_not_glade, tmp_path):

    assert ProductRegistry.validate_function(
        "cesm_ocean_output", "get_cesm_single_variable_data"
    )


def _write_mom6_history_file(
    path, lat_min=20, lat_max=25, lon_min=-90, lon_max=-85, ntime=10
):
    """Writes a synthetic multi-variable native MOM6 history file (one file, many vars)."""
    time = pd.date_range("2000-01-01", periods=ntime, freq="D")
    yh = np.linspace(lat_min, lat_max, 6)
    xh = np.linspace(lon_min, lon_max, 6)
    z_l = np.array([5.0, 50.0])
    shape_3d = (ntime, len(z_l), len(yh), len(xh))
    shape_2d = (ntime, len(yh), len(xh))
    ds = xr.Dataset(
        {
            "thetao": (("time", "z_l", "yh", "xh"), np.random.rand(*shape_3d)),
            "so": (("time", "z_l", "yh", "xh"), np.random.rand(*shape_3d)),
            "uo": (("time", "z_l", "yh", "xh"), np.random.rand(*shape_3d)),
            "vo": (("time", "z_l", "yh", "xh"), np.random.rand(*shape_3d)),
            "zos": (("time", "yh", "xh"), np.random.rand(*shape_2d)),
        },
        coords={"time": time, "z_l": z_l, "yh": yh, "xh": xh},
    )
    ds.to_netcdf(path)
    return path


def test_get_mom6_output_data_missing_dataset_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        co.CESM_OCEAN_OUTPUT.get_mom6_output_data(
            dates=["2000-01-01", "2000-01-10"],
            lat_min=20,
            lat_max=25,
            lon_min=-90,
            lon_max=-85,
            output_folder=tmp_path,
            dataset_path=tmp_path / "does_not_exist",
        )


def test_get_mom6_output_data_no_matching_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        co.CESM_OCEAN_OUTPUT.get_mom6_output_data(
            dates=["2000-01-01", "2000-01-10"],
            lat_min=20,
            lat_max=25,
            lon_min=-90,
            lon_max=-85,
            output_folder=tmp_path,
            dataset_path=tmp_path,
            file_glob="no_such_files*.nc",
        )


def test_get_mom6_output_data_reads_multi_var_file(tmp_path):
    lat_min, lat_max, lon_min, lon_max = 20, 25, -90, -85
    _write_mom6_history_file(
        tmp_path / "test_case.region.nc", lat_min, lat_max, lon_min, lon_max
    )

    paths = co.CESM_OCEAN_OUTPUT.get_mom6_output_data(
        dates=["2000-01-01", "2000-01-10"],
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        output_folder=tmp_path,
        output_filename="out.nc",
        variables=["thetao", "so", "uo", "vo", "zos"],
        dataset_path=tmp_path,
        file_glob="test_case.region*.nc",
    )

    ds = xr.open_dataset(paths[0])
    for var in ["thetao", "so", "uo", "vo", "zos"]:
        assert var in ds.data_vars
    assert ds.yh.max() <= lat_max + 1.5
    assert ds.yh.min() >= lat_min - 1.5
    assert ds.xh.max() <= lon_max + 1.5
    assert ds.xh.min() >= lon_min - 1.5


def test_get_mom6_output_data_drops_missing_variables(tmp_path):
    lat_min, lat_max, lon_min, lon_max = 20, 25, -90, -85
    _write_mom6_history_file(
        tmp_path / "test_case.region.nc", lat_min, lat_max, lon_min, lon_max
    )

    paths = co.CESM_OCEAN_OUTPUT.get_mom6_output_data(
        dates=["2000-01-01", "2000-01-10"],
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        output_folder=tmp_path,
        output_filename="out.nc",
        variables=["thetao", "not_a_real_variable"],
        dataset_path=tmp_path,
        file_glob="test_case.region*.nc",
    )

    ds = xr.open_dataset(paths[0])
    assert "thetao" in ds.data_vars
    assert "not_a_real_variable" not in ds.data_vars


@pytest.mark.slow
def test_get_mom6_output_data_validation():
    ProductRegistry.load()
    assert ProductRegistry.validate_function(
        "cesm_ocean_output", "get_mom6_output_data"
    )


def test_parse_dataset(tmp_path, dummy_forcing_factory):

    ds = dummy_forcing_factory(
        36,
        56,
        36,
        56,
    )
    ds.to_netcdf(tmp_path / "east.DOC.20200101.20200102.nc")
    ds.to_netcdf(tmp_path / "west.DOC.20200101.20200102.nc")
    ds.to_netcdf(tmp_path / "north.DIC.20200101.20200102.nc")
    ds.to_netcdf(tmp_path / "south.DIC.20200101.20200102.nc")

    # Generate datasets

    vars = ["DIC", "DOC"]
    variable_info = co.parse_dataset(
        vars, tmp_path, "20200101", "20200131", regex=r"(\d{6,8}).(\d{6,8})"
    )

    assert str(tmp_path / "north.DIC.20200101.20200102.nc") in variable_info["DIC"]
    assert str(tmp_path / "west.DOC.20200101.20200102.nc") in variable_info["DOC"]


def test_subset_dataset(dummy_forcing_factory, get_rect_grid, tmp_path):

    ds = dummy_forcing_factory(
        0,
        15,
        270,
        300,
    )
    ds.to_netcdf(tmp_path / "east.thetao.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path / "west.thetao.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path / "north.so.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path / "south.so.20200101.20200102.nc")

    # Generate datasets

    vars = ["so", "thetao"]
    variable_info = co.parse_dataset(
        vars, tmp_path, "20200101", "20200131", regex=r"(\d{6,8}).(\d{6,8})"
    )

    grid = get_rect_grid
    boundary_info = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    co.subset_dataset(
        variable_info=variable_info,
        output_path=tmp_path,
        lat_min=boundary_info["ic"]["lat_min"] - 1,
        lat_max=boundary_info["ic"]["lat_max"] + 1,
        lon_min=boundary_info["ic"]["lon_min"] - 1,
        lon_max=boundary_info["ic"]["lon_max"] + 1,
        lat_name="latitude",
        lon_name="longitude",
        preview=False,
    )
    assert any(p.name.startswith("so_subset") for p in tmp_path.glob("*.nc"))
    assert any(p.name.startswith("thetao_subset") for p in tmp_path.glob("*.nc"))
    matches = list(tmp_path.glob("thetao_subset*.nc"))
    ds = xr.open_dataset(matches[0])
    assert ds["latitude"].max() < boundary_info["ic"]["lat_max"] + 2
    assert ds["latitude"].min() > boundary_info["ic"]["lat_min"] - 2
    assert len(ds.time) == 64
