from CrocoDash.raw_data_access.datasets import glorys as gl
from CrocoDash.raw_data_access.region import Region
from CrocoDash.raw_data_access.time_request import TimeRequest
import os
import pytest
import xarray as xr
import numpy as np


def _fake_full_globe_ds():
    lat = np.array([30.0, 31.0])
    lon = np.arange(-180.0, 180.0, 1.0)
    zos = np.broadcast_to(lon, (1, len(lat), len(lon))).copy()
    return xr.Dataset(
        {"zos": (("time", "latitude", "longitude"), zos)},
        coords={"time": [0], "latitude": lat, "longitude": lon},
    )


def test_rda_box_across_180(tmp_path, monkeypatch):
    """A box across 180E (170..190, padded by buf=1.0) comes back as 169..191,
    west to east and each column once. Each source column's data is its own
    longitude, so a column moved without its label (a mirrored seam) shows
    up."""
    monkeypatch.setattr(gl.glob, "glob", lambda *a, **k: ["dummy.nc"])
    monkeypatch.setattr(gl.xr, "open_mfdataset", lambda *a, **k: _fake_full_globe_ds())

    dataset_path = gl.GLORYS.get_glorys_data_from_rda(
        region=Region(30, 31, 170, 190),
        when=TimeRequest("2000-01-01", "2000-01-01"),
        output_folder=tmp_path,
        output_filename="temp.nc",
        variables=["zos"],
    )
    result = xr.open_dataset(dataset_path)
    out_lon = result.longitude.values

    np.testing.assert_array_equal(out_lon, np.arange(169.0, 192.0))
    np.testing.assert_array_equal(
        result.zos.isel(time=0, latitude=0).values, (out_lon + 180) % 360 - 180
    )


def test_get_glorys_data_from_rda_reads_only_the_sampled_days(tmp_path, monkeypatch):
    """A when thinned to "MS" reads the month starts in the window and
    nothing else; without dates it reads every day."""
    requested = []
    monkeypatch.setattr(
        gl.glob, "glob", lambda pattern: requested.append(pattern) or ["dummy.nc"]
    )
    monkeypatch.setattr(gl.xr, "open_mfdataset", lambda *a, **k: _fake_full_globe_ds())

    def days_read(when):
        requested.clear()
        gl.GLORYS.get_glorys_data_from_rda(
            region=Region(30, 31, 10, 20),
            when=when,
            output_folder=tmp_path,
            output_filename="temp.nc",
            variables=["zos"],
        )
        return [os.path.basename(pattern).split("_")[1] for pattern in requested]

    window = ("2020-01-10", "2020-03-05")
    assert days_read(TimeRequest.every("MS", *window)) == ["20200201", "20200301"]
    daily = days_read(TimeRequest(*window))
    assert (len(daily), daily[0], daily[-1]) == (56, "20200110", "20200305")


@pytest.mark.slow
def test_get_glorys_data_from_rda(skip_if_not_glade, tmp_path):
    lat_min = 30
    lat_max = 31
    lon_min = -71
    lon_max = -70
    dataset_path = gl.GLORYS.get_glorys_data_from_rda(
        region=Region(lat_min, lat_max, lon_min, lon_max),
        when=TimeRequest("2000-01-01", "2000-01-05"),
        output_folder=tmp_path,
        output_filename="temp.nc",
    )
    dataset = xr.open_dataset(dataset_path)
    assert dataset.time.values[0] == np.datetime64("2000-01-01T12:00:00.000000000")
    assert dataset.time.values[-1] == np.datetime64("2000-01-05T12:00:00.000000000")
    assert np.abs(dataset.latitude.values[-1] - lat_max) <= 1
    assert np.abs(dataset.latitude.values[0] - lat_min) <= 1
    assert np.abs(dataset.longitude.values[-1] - lon_max) <= 1
    assert np.abs(dataset.longitude.values[0] - lon_min) <= 1


@pytest.mark.slow
def test_get_glorys_data_from_cds_api(tmp_path):
    lat_min = 60
    lat_max = 61
    lon_min = -35
    lon_max = -34
    res = gl.GLORYS.get_glorys_data_from_cds_api(
        region=Region(lat_min, lat_max, lon_min, lon_max),
        when=TimeRequest("2000-01-01", "2000-01-05"),
        output_folder=tmp_path,
        output_filename="temp.nc",
    )
    dataset = xr.open_dataset(res)
    assert dataset.time.values[0] == np.datetime64("2000-01-01T00:00:00.000000000")
    assert dataset.time.values[-1] == np.datetime64("2000-01-05T00:00:00.000000000")
    assert dataset.latitude.values[-1] == lat_max + 1
    assert dataset.latitude.values[0] == lat_min - 1
    assert dataset.longitude.values[-1] == lon_max + 1
    assert dataset.longitude.values[0] == lon_min - 1


def test_cli_script_keeps_every_request(tmp_path):
    """Each call adds its own subset line to one get_glorys_data.sh, so a
    second chunk or boundary doesn't overwrite the first; asking again for
    one already in it adds nothing."""

    def request(start, end, filename):
        return gl.GLORYS.get_glorys_data_script_for_cli(
            region=Region(3, 61, -101, -34),
            when=TimeRequest(start, end),
            output_folder=tmp_path,
            output_filename=filename,
        )

    request("2000-01-01", "2000-01-07", "east_1.nc")
    request("2000-01-08", "2000-01-14", "east_2.nc")
    path = request("2000-01-01", "2000-01-07", "east_1.nc")

    lines = [line for line in path.read_text().splitlines() if "subset" in line]
    assert [line.split(" -f ")[-1] for line in lines] == ["east_1.nc", "east_2.nc"]
    assert "--end-datetime 2000-01-14T23:59:59" in lines[1]
