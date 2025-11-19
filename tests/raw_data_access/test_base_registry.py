import pytest
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import BaseProduct, ForcingProduct


# --- Dummy product for testing ---
class DummyProduct(BaseProduct):
    product_name = "dummy"
    description = "A dummy product for testing"

    @BaseProduct.access_method("dummy_method")
    def dummy_method(dates, output_folder, output_filename):
        return f"{dates[0]}{dates[1]}{output_folder}/{output_filename}"

# Dummy concrete forcing product
class DummyForcing(ForcingProduct):
    product_name = "dummy_forcing"
    description = "Dummy forcing product for testing"
    time_var_name = "time"
    u_x_coord = "xu"
    u_y_coord = "yu"
    v_x_coord = "xv"
    v_y_coord = "yv"
    tracer_x_coord = "xt"
    tracer_y_coord = "yt"
    depth_coord = "depth"
    u_var_name = "u"
    v_var_name = "v"
    eta_var_name = "eta"
    tracer_var_names = {"temp": "theta", "salt": "salt"}
    boundary_fill_method = "nearest"
    time_units = "days since 2000-01-01"

    @ForcingProduct.access_method("fetch_dummy")
    def fetch_dummy(output_folder, output_filename, variables, lon_max, lat_max, lon_min, lat_min):
        return f"Fetched {variables} to {output_folder}/{output_filename}"
# by default the products should be registered


# --- Tests ---
def test_list_products():
    assert "dummy" in ProductRegistry.list_products()


def test_get_product():
    cls = ProductRegistry.get_product("dummy")
    assert cls is DummyProduct


def test_list_access_methods():
    methods = ProductRegistry.list_access_methods("dummy")
    assert "dummy_method" in methods


def test_call_access_method_success():
    result = ProductRegistry.call(
        "dummy",
        "dummy_method",
        dates=["asd", "asd"],
        output_folder="/tmp",
        output_filename="file.nc",
    )
    assert result == "asdasd/tmp/file.nc"


def test_call_access_method_missing_arg():
    with pytest.raises(ValueError):
        ProductRegistry.call(
            "dummy", "dummy_method", output_folder="/tmp"  # missing output_filename
        )


def test_call_nonexistent_method():
    with pytest.raises(KeyError):
        ProductRegistry.call("dummy", "nonexistent_method")

# def test_call_access_method_success():
#     result = ProductRegistry.call(
#         "dummy_forcing",
#         "fetch_dummy",
#         output_folder="/tmp",
#         output_filename="file.nc",
#         variables=["temp", "salt"],
#         lon_max=10,
#         lat_max=20,
#         lon_min=0,
#         lat_min=0,
#     )
#     assert "Fetched" in result
#     assert "/tmp/file.nc" in result