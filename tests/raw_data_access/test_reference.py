import numpy as np
import pytest
import xarray as xr
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.datasets.reference import REFERENCE_OCEAN

BBOX = dict(lat_min=10.0, lat_max=15.0, lon_min=-30.0, lon_max=-25.0)
DATES = ["2020-01-01", "2020-01-02"]


def test_reference_products_registered():
    ProductRegistry.load()
    assert "reference_ocean" in ProductRegistry.list_products()


@pytest.mark.parametrize(
    "cls,method_name",
    [
        (REFERENCE_OCEAN, "get_reference_ocean_data"),
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
