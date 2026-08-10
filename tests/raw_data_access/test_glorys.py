from CrocoDash.raw_data_access.datasets import glorys as gl
import os
import pytest
import xarray as xr
import numpy as np


def test_get_glorys_data_from_rda_antimeridian_wrap_no_mirror(tmp_path, monkeypatch):
    """A box that wraps the antimeridian (lon_min > lon_max, e.g. 170..-170)
    splits into an eastern (169..180) and western (-180..-169) slice, then
    shifts the western slice into 180..191 so the concatenated result sorts
    into one ascending run across the seam. The shift must be `lon % 360`
    (a pure translation) -- `(360 - lon) % 360` is a reflection that swaps
    which hemisphere's data ends up on which side of the dateline, and a
    plain "sorted, no duplicate longitudes" check can't tell the two apart
    since both produce the same set of longitude *values*, just paired with
    the wrong data.

    Tags each raw longitude's data with its own (unshifted, native -180..180)
    value, so after the transform we can check the data followed its label
    instead of only checking the label set.
    """
    lat = np.array([30.0, 31.0])
    lon = np.arange(-180.0, 181.0, 1.0)
    zos = np.broadcast_to(lon, (1, len(lat), len(lon))).copy()
    fake_ds = xr.Dataset(
        {"zos": (("time", "latitude", "longitude"), zos)},
        coords={"time": [0], "latitude": lat, "longitude": lon},
    )

    monkeypatch.setattr(gl.glob, "glob", lambda *a, **k: ["dummy.nc"])
    monkeypatch.setattr(gl.xr, "open_mfdataset", lambda *a, **k: fake_ds)

    dataset_path = gl.GLORYS.get_glorys_data_from_rda(
        ["2000-01-01", "2000-01-01"],
        30,
        31,
        170,
        -170,
        output_folder=tmp_path,
        output_filename="temp.nc",
        variables=["zos"],
    )
    result = xr.open_dataset(dataset_path)
    out_lon = result.longitude.values
    out_zos = result.zos.isel(time=0, latitude=0).values

    assert np.all(np.diff(out_lon) >= 0)  # ascending across the seam

    for final_lon, value in zip(out_lon, out_zos):
        # 180 is a shared boundary point: it's produced both by the eastern
        # slice's own 180 and by the western slice's -180 mapping to 180, so
        # either raw value is valid there.
        if final_lon == 180.0:
            assert value in (
                pytest.approx(180.0),
                pytest.approx(-180.0),
            ), f"longitude 180 carries unexpected raw longitude {value}"
            continue
        expected_raw = final_lon if final_lon < 180 else final_lon - 360
        assert value == pytest.approx(expected_raw), (
            f"longitude {final_lon} carries data from raw longitude {value}, "
            f"expected {expected_raw} -- data did not follow its label across "
            "the antimeridian shift"
        )


def _fake_full_globe_ds():
    lat = np.array([30.0, 31.0])
    lon = np.arange(-180.0, 181.0, 1.0)
    zos = np.broadcast_to(lon, (1, len(lat), len(lon))).copy()
    return xr.Dataset(
        {"zos": (("time", "latitude", "longitude"), zos)},
        coords={"time": [0], "latitude": lat, "longitude": lon},
    )


def test_get_glorys_data_from_rda_lon_max_exactly_180_is_not_a_wrap(
    tmp_path, monkeypatch
):
    """convert_lons_to_180_range maps a lon_max of exactly 180 to -180 (both
    represent the same meridian). A box like 100..180 must still take the
    contiguous (non-wrap) branch instead of being misrouted into the
    split/concat wrap branch by that relabeling.
    """
    fake_ds = _fake_full_globe_ds()
    monkeypatch.setattr(gl.glob, "glob", lambda *a, **k: ["dummy.nc"])
    monkeypatch.setattr(gl.xr, "open_mfdataset", lambda *a, **k: fake_ds)

    dataset_path = gl.GLORYS.get_glorys_data_from_rda(
        ["2000-01-01", "2000-01-01"],
        30,
        31,
        100,
        180,
        output_folder=tmp_path,
        output_filename="temp.nc",
        variables=["zos"],
    )
    result = xr.open_dataset(dataset_path)
    out_lon = result.longitude.values

    assert out_lon.min() == pytest.approx(99.0)  # lon_min - 1 buffer
    assert out_lon.max() == pytest.approx(180.0)  # native range caps at 180
    assert len(out_lon) == len(np.unique(out_lon))  # no wrap-branch duplicates


def test_get_glorys_data_from_rda_near_global_box_has_no_duplicate_longitudes(
    tmp_path, monkeypatch
):
    """A near-full-circle box (lon_min/lon_max both close to the same
    meridian, e.g. 0.5..-0.5) leaves an excluded gap narrower than the
    combined 2deg buffer, so the wrap branch's two slices overlap and would
    otherwise duplicate longitude values around the gap edges.
    """
    fake_ds = _fake_full_globe_ds()
    monkeypatch.setattr(gl.glob, "glob", lambda *a, **k: ["dummy.nc"])
    monkeypatch.setattr(gl.xr, "open_mfdataset", lambda *a, **k: fake_ds)

    dataset_path = gl.GLORYS.get_glorys_data_from_rda(
        ["2000-01-01", "2000-01-01"],
        30,
        31,
        0.5,
        -0.5,
        output_folder=tmp_path,
        output_filename="temp.nc",
        variables=["zos"],
    )
    result = xr.open_dataset(dataset_path)
    out_lon = result.longitude.values

    assert len(out_lon) == len(np.unique(out_lon))


@pytest.mark.slow
def test_get_glorys_data_from_rda(skip_if_not_glade, tmp_path):
    dates = ["2000-01-01", "2000-01-05"]
    lat_min = 30
    lat_max = 31
    lon_min = -71
    lon_max = -70
    dataset_path = gl.GLORYS.get_glorys_data_from_rda(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
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
    dates = ["2000-01-01", "2000-01-05"]
    lat_min = 60
    lat_max = 61
    lon_min = -35
    lon_max = -34
    res = gl.GLORYS.get_glorys_data_from_cds_api(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
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


def test_get_glorys_data_script_for_cli(tmp_path):
    dates = ["2000-01-01", "2020-12-31"]
    lat_min = 3
    lat_max = 61
    lon_min = -101
    lon_max = -34
    path = gl.GLORYS.get_glorys_data_script_for_cli(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        output_folder=tmp_path,
        output_filename="temp",
    )

    # Just testing if it exists, this function just calls a regional_mom6 function
    assert os.path.exists(path)
