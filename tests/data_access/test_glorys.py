from CrocoDash.data_access import glorys as gl
import pandas as pd
import os



def test_get_glorys_data_from_rda():
    dates = ["2005-01-01", "2005-01-05"]
    lat_min = 30
    lat_max = 31
    lon_min = -71
    lon_max = -70
    dataset = gl.get_glorys_data_from_rda(
        pd.date_range(start=dates[0], end=dates[1]).to_pydatetime().tolist(),
        lat_min,
        lat_max,
        lon_min,
        lon_max,
    )
    print(dataset)


def test_get_glorys_data_from_cds_api():
    dates = ["2000-01-01", "2020-12-31"]
    lat_min = 3
    lat_max = 61
    lon_min = -101
    lon_max = -34
    dataset = gl.get_glorys_data_from_cds_api(dates, lat_min, lat_max, lon_min, lon_max)
    assert dataset

def test_get_glorys_data_script_for_cli(tmp_path):
    dates = ["2000-01-01", "2020-12-31"]
    lat_min = 3
    lat_max = 61
    lon_min = -101
    lon_max = -34
    gl.get_glorys_data_script_for_cli(dates, lat_min, lat_max, lon_min, lon_max,segment_name = "temp.nc", download_path=tmp_path)
    assert os.path.exists(tmp_path/"get_glorys_data.sh")
