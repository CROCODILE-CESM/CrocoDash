import numpy as np
import pytest
import xarray as xr
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.datasets.reference import (
    REFERENCE_OCEAN,
    REFERENCE_WAVES,
)

BBOX = dict(lat_min=10.0, lat_max=15.0, lon_min=-30.0, lon_max=-25.0)
DATES = ["2020-01-01", "2020-01-02"]


def test_reference_products_registered():
    ProductRegistry.load()
    for name in ("reference_ocean", "reference_waves"):
        assert name in ProductRegistry.list_products()


@pytest.mark.parametrize(
    "cls,method_name",
    [
        (REFERENCE_OCEAN, "get_reference_ocean_data"),
        (REFERENCE_WAVES, "get_reference_wave_spectra"),
    ],
)
def test_write_metadata_has_required_fields(cls, method_name):
    metadata = cls.write_metadata()
    missing = [arg for arg in cls.required_metadata if arg not in metadata]
    assert not missing, f"Missing required metadata: {missing}"
    assert method_name in cls._access_methods


@pytest.mark.parametrize(
    "cls,method_name",
    [
        (REFERENCE_OCEAN, "get_reference_ocean_data"),
        (REFERENCE_WAVES, "get_reference_wave_spectra"),
    ],
)
def test_validate_method_toy_call_succeeds(cls, method_name):
    assert cls.validate_method(method_name)


def test_reference_ocean_shape_and_thermocline(tmp_path):
    path = REFERENCE_OCEAN.get_reference_ocean_data(
        dates=DATES, output_folder=tmp_path, output_filename="ocean.nc", **BBOX
    )
    ds = xr.open_dataset(path)
    assert ds.sizes["time"] == 2
    for var in ("temp", "salt", "u", "v", "ssh"):
        assert var in ds
    # Warm surface decaying to a cold abyssal floor -- a rough thermocline.
    surface = ds["temp"].isel(time=0, depth=0).values
    deep = ds["temp"].isel(time=0, depth=-1).values
    assert np.all(surface > deep)


def test_reference_ocean_variables_filter(tmp_path):
    path = REFERENCE_OCEAN.get_reference_ocean_data(
        dates=DATES,
        output_folder=tmp_path,
        output_filename="ocean.nc",
        variables=["temp", "salt"],
        **BBOX,
    )
    ds = xr.open_dataset(path)
    assert set(ds.data_vars) == {"temp", "salt"}


def test_reference_ocean_is_deterministic(tmp_path):
    path_a = REFERENCE_OCEAN.get_reference_ocean_data(
        dates=DATES, output_folder=tmp_path, output_filename="a.nc", **BBOX
    )
    path_b = REFERENCE_OCEAN.get_reference_ocean_data(
        dates=DATES, output_folder=tmp_path, output_filename="b.nc", **BBOX
    )
    ds_a, ds_b = xr.open_dataset(path_a), xr.open_dataset(path_b)
    xr.testing.assert_identical(ds_a, ds_b)


def test_reference_waves_shape_and_peak(tmp_path):
    path = REFERENCE_WAVES.get_reference_wave_spectra(
        dates=DATES, output_folder=tmp_path, output_filename="waves.nc", **BBOX
    )
    ds = xr.open_dataset(path)
    (var_name,) = ds.data_vars
    da = ds[var_name]
    assert set(da.dims) == {"time", "latitude", "longitude", "frequency", "direction"}
    # JONSWAP spectrum should peak near fp = 1/Tp = 0.125 Hz, not at the edges.
    spectrum_by_freq = da.isel(time=0, latitude=0, longitude=0).sum(dim="direction")
    peak_freq = float(ds["frequency"][spectrum_by_freq.argmax(dim="frequency")])
    assert 0.08 < peak_freq < 0.2
