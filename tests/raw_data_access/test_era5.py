import os

import numpy as np
import pandas as pd
import pytest

from CrocoDash.raw_data_access.datasets import era5
from CrocoDash.raw_data_access.registry import ProductRegistry

# Bering Sea demo case bounding box (dev/cice_obc_demo/cice_with_obcs.ipynb).
_LAT_MIN, _LAT_MAX = 68, 78
_LON_MIN, _LON_MAX = -170, -155


def test_build_era5_spectra_request_area_order():
    request = era5.build_era5_spectra_request(
        ["2020-01-01", "2020-01-01"], _LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX
    )
    assert request["area"] == "79.0/-171.0/67.0/-154.0"


def test_build_era5_spectra_request_custom_buffer():
    request = era5.build_era5_spectra_request(
        ["2020-01-01", "2020-01-01"],
        _LAT_MIN,
        _LAT_MAX,
        _LON_MIN,
        _LON_MAX,
        buffer_deg=0.0,
    )
    assert request["area"] == "78.0/-170.0/68.0/-155.0"


def test_build_era5_spectra_request_single_day():
    request = era5.build_era5_spectra_request(
        ["2020-01-15", "2020-01-15"], _LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX
    )
    assert request["date"] == "2020-01-15/to/2020-01-15"


def test_build_era5_spectra_request_multi_day():
    request = era5.build_era5_spectra_request(
        ["2020-01-30", "2020-02-02"], _LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX
    )
    assert request["date"] == "2020-01-30/to/2020-02-02"


def test_build_era5_spectra_request_fixed_mars_keys():
    request = era5.build_era5_spectra_request(
        ["2020-01-01", "2020-01-01"], _LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX
    )
    assert request["class"] == "ea"
    assert request["expver"] == "1"
    assert request["stream"] == "wave"
    assert request["type"] == "an"
    assert request["levtype"] == "sfc"
    assert request["param"] == "251.140"
    assert request["time"] == "00/to/23/by/1"
    assert request["direction"] == "1/to/24"
    assert request["frequency"] == "1/to/30"
    assert request["data_format"] == "grib"
    assert request["grid"] == "0.5/0.5"


def test_era5_wave_spectra_registered():
    ProductRegistry.load()
    assert "era5_wave_spectra" in ProductRegistry.list_products()
    assert "get_era5_2d_spectra" in ProductRegistry.list_access_methods(
        "era5_wave_spectra"
    )


def test_write_metadata_includes_required_fields():
    meta = era5.ERA5_WAVE_SPECTRA.write_metadata()
    missing = [f for f in era5.ERA5_WAVE_SPECTRA.required_metadata if f not in meta]
    assert not missing


@pytest.mark.slow
def test_get_era5_2d_spectra(tmp_path):
    """Real network call against cds.climate.copernicus.eu's
    reanalysis-era5-complete. Expected to fail unless a separate CDS API key
    (with reanalysis-era5-complete access accepted) is active for this
    process, e.g. via a CDSAPI_RC env var pointing at an alternate rc file --
    the default ~/.cdsapirc on this system points at
    ewds.climate.copernicus.eu (used by the existing GLOFAS product), not
    the main CDS. Same situation GLOFAS's/GLORYS's own slow tests are
    already in without their credentials -- do not mock cdsapi.Client to
    fake a pass here. Confirmed working end-to-end (real download + decode)
    on 2026-08-03 with a correctly-scoped CDSAPI_RC.
    """
    path = era5.ERA5_WAVE_SPECTRA.get_era5_2d_spectra(
        dates=["2020-01-01", "2020-01-01"],
        lat_min=_LAT_MIN,
        lat_max=_LAT_MAX,
        lon_min=_LON_MIN,
        lon_max=_LON_MAX,
        output_folder=tmp_path,
        output_filename="era5_spectra_test.nc",
    )
    assert os.path.exists(path)
    import xarray as xr

    ds = xr.open_dataset(path)
    try:
        assert set(ds["efth"].dims) == {
            "time",
            "latitude",
            "longitude",
            "frequency",
            "direction",
        }
    finally:
        ds.close()


def _fake_era5_message(
    direction_number, frequency_number, timestamp, value, n_lat, n_lon
):
    """One fabricated GRIB-message ingredient for _assemble_era5_dataset,
    matching what _read_era5_grib_messages hands it -- (values, missing_value).
    """
    missing_value = 9999.0
    grid = np.full(n_lat * n_lon, missing_value if value is None else value)
    return (direction_number, frequency_number, timestamp), (grid, missing_value)


def test_assemble_era5_dataset_decodes_log10_and_missing():
    """Pure decode logic, no real GRIB file needed: builds a tiny fabricated
    set of "messages" -- one real (log10-encoded) value, one missing -- and
    checks _assemble_era5_dataset decodes 10**value where present and 0.0
    where the missing-value sentinel was hit.
    """
    directions = np.array([7.5, 22.5])
    frequencies = np.array([0.0345, 0.038])
    latitudes = np.array([69.0])
    longitudes = np.array([-170.0, -169.5])
    t0 = pd.Timestamp("2020-01-01T00:00:00")

    raw = {}
    key, val = _fake_era5_message(1, 1, t0, -2.0, n_lat=1, n_lon=2)
    raw[key] = val
    key, val = _fake_era5_message(2, 1, t0, None, n_lat=1, n_lon=2)  # missing
    raw[key] = val

    ds = era5._assemble_era5_dataset(
        directions=directions,
        frequencies=frequencies,
        latitudes=latitudes,
        longitudes=longitudes,
        n_lat=1,
        n_lon=2,
        times=[t0],
        raw=raw,
    )

    assert set(ds["efth"].dims) == {
        "time",
        "latitude",
        "longitude",
        "frequency",
        "direction",
    }
    real = ds["efth"].sel(direction=7.5, frequency=0.0345).values
    assert np.allclose(real, 10.0**-2.0)
    missing = ds["efth"].sel(direction=22.5, frequency=0.0345).values
    assert np.allclose(missing, 0.0)
