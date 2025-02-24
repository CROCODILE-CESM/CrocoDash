from CrocoDash.data_access import glorys as gl
import pandas as pd
import os
import pytest
import xarray as xr
import numpy as np


def test_get_glorys_data_from_rda(check_glade_exists, tmp_path):
    dates = ["2000-01-01", "2000-01-05"]
    lat_min = 30
    lat_max = 31
    lon_min = -71
    lon_max = -70
    dataset_path = gl.get_glorys_data_from_rda(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        tmp_path,
        "temp.nc"
    )
    dataset = xr.open_dataset(dataset_path)
    assert dataset.time.values[0] == np.datetime64('2000-01-01T12:00:00.000000000')
    assert dataset.time.values[-1] == np.datetime64('2000-01-05T12:00:00.000000000')
    assert dataset.latitude.values[-1] == lat_max
    assert dataset.latitude.values[0] == lat_min
    assert dataset.longitude.values[-1] == lon_max
    assert dataset.longitude.values[0] == lon_min


@pytest.mark.slow
def test_get_glorys_data_from_cds_api(tmp_path):
    dates = ["2000-01-01", "2000-01-05"]
    lat_min = 60
    lat_max = 61
    lon_min = -35
    lon_max = -34
    res = gl.get_glorys_data_from_cds_api(
        dates,
        lon_min,
        lon_max,
        lat_min,
        lat_max,
        output_dir=tmp_path,
        output_file="temp.nc",
    )
    breakpoint()
    dataset = xr.open_dataset(tmp_path / "temp.nc")
    assert dataset.time.values[0] == np.datetime64("2000-01-01T00:00:00.000000000")
    assert dataset.time.values[-1] == np.datetime64("2000-01-05T00:00:00.000000000")
    assert dataset.latitude.values[-1] == lat_max
    assert dataset.latitude.values[0] == lat_min
    assert dataset.longitude.values[-1] == lon_max
    assert dataset.longitude.values[0] == lon_min


def test_get_glorys_data_script_for_cli(tmp_path):
    dates = ["2000-01-01", "2020-12-31"]
    lat_min = 3
    lat_max = 61
    lon_min = -101
    lon_max = -34
    path = gl.get_glorys_data_script_for_cli(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        output_dir = tmp_path,
        output_file = "temp"
    )

    # Just testing if it exists, this function just calls a regional_mom6 function
    assert os.path.exists(path)
