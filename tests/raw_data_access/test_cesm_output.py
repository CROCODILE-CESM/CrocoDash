from CrocoDash.raw_data_access.datasets import cesm_output as co 
from CrocoDash.raw_data_access import driver as dv
import xarray as xr
import pytest 
import numpy as np
import cftime
@pytest.mark.slow
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
    

def test_get_cesm_data_validation(skip_if_not_glade,tmp_path):
    pfd_obj = dv.ProductFunctionRegistry()
    pfd_obj.load_functions()
    assert  pfd_obj.validate_function("CESM_OUTPUT", "get_cesm_data")
