from CrocoDash.raw_data_access.datasets import cesm_output as co 
from CrocoDash.raw_data_access import driver as dv
import xarray as xr
import pytest 
import numpy as np
import cftime
from pathlib import Path
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info

def test_get_cesm_data(skip_if_not_glade, tmp_path):
    dates = ["2000-01-01", "2000-01-05"]
    lat_min = 30
    lat_max = 31
    lon_min = 289
    lon_max = 290
    paths = co.get_cesm_data(
        dates, lat_min, lat_max, lon_min, lon_max, tmp_path, "temp.nc",variables=["SSH"]
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
        f"({time_vals[0]} to {time_vals[-1]})")
    assert np.abs(dataset.TLAT.values[-1,0] - lat_max) <= 4
    assert np.abs(dataset.TLAT.values[0,0] - lat_min) <= 4
    assert np.abs(dataset.TLONG.values[0,-1] - lon_max) <= 4
    assert np.abs(dataset.TLONG.values[0,0] - lon_min) <= 4
    
@pytest.mark.slow
def test_get_cesm_data_validation(skip_if_not_glade,tmp_path):
    pfd_obj = dv.ProductFunctionRegistry()
    pfd_obj.load_functions()
    assert  pfd_obj.validate_function("CESM_OUTPUT", "get_cesm_data")

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
    boundary_info = get_rectangular_segment_info(grid)
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