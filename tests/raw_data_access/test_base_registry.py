import pytest
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import *


# --- Dummy product for testing ---
class DummyProduct(DatedBaseProduct):
    product_name = "dummy"
    description = "A dummy product for testing"
    link = "dummy_link"
    time_sampling = None

    @accessmethod
    def dummy_method(dates, output_folder, output_filename, freq=None):
        return f"{dates[0]}{dates[1]}{output_folder}/{output_filename}"


# Dummy concrete forcing product
class DummyForcing(MOM6ForcingProduct):
    link = "dummy_link"
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
    calendar = GREGORIAN
    time_sampling = TimeSampling("D")

    @accessmethod
    def fetch_dummy(
        dates,
        output_folder,
        output_filename,
        lon_max,
        lat_max,
        lon_min,
        lat_min,
        name=None,
        variables="SSH",
        freq=None,
    ):
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


def test_call_access_method_success_basic():
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


def test_call_access_method_success():
    result = ProductRegistry.call(
        "dummy_forcing",
        "fetch_dummy",
        dates=["!23", "123"],
        output_folder="/tmp",
        output_filename="file.nc",
        variables=["temp", "salt"],
        lon_max=10,
        lat_max=20,
        lon_min=0,
        lat_min=0,
        name="north",
    )
    assert "Fetched" in result
    assert "/tmp/file.nc" in result


def test_tracer_names_check():
    # Dummy concrete forcing product with broken tracer names
    with pytest.raises(AssertionError):

        class DummyForcing(MOM6ForcingProduct):
            link = "dummy_link"
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
            tracer_var_names = {"not_temp": "theta", "salt": "salt"}
            boundary_fill_method = "nearest"
            time_units = "days since 2000-01-01"
            calendar = GREGORIAN
            time_sampling = TimeSampling("D")


def test_write_metadata():
    dummy_forcing_dict = DummyForcing.write_metadata()
    # Check that every required_arg is present as a key
    missing = [
        arg for arg in DummyForcing.required_metadata if arg not in dummy_forcing_dict
    ]
    assert not missing, f"Missing required args in metadata: {missing}"


def test_validate_method():
    assert DummyProduct.validate_method("dummy_method")


def test_forcing_validate_method():
    assert DummyForcing.validate_method("fetch_dummy")


def test_validate_method_removes_its_temporary_directory(tmp_path, monkeypatch):
    temp_dir = tmp_path / "toy"
    temp_dir.mkdir()
    monkeypatch.setattr("tempfile.mkdtemp", lambda: str(temp_dir))
    assert DummyForcing.validate_method("fetch_dummy")
    assert not temp_dir.exists()


def test_forcing_validate_method_passes_overrides_through(monkeypatch):
    """A product overriding validate_method (e.g. for in-range dates) relies
    on ForcingProduct forwarding its kwargs to the toy call."""
    received = {}
    monkeypatch.setitem(
        DummyForcing._access_methods,
        "fetch_dummy",
        staticmethod(lambda **kwargs: received.update(kwargs)),
    )
    assert DummyForcing.validate_method("fetch_dummy", variables="SST") is True
    assert received["variables"] == "SST"


def test_validate_method_returns_a_bool_not_the_toy_calls_result():
    """The toy call's result (typically a path) points into the temporary
    directory, which is gone by the time validate_method returns."""
    assert DummyForcing.validate_method("fetch_dummy") is True


def test_validate_method_returns_false_when_the_toy_call_raises(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("no credentials")

    monkeypatch.setitem(DummyForcing._access_methods, "fetch_dummy", staticmethod(fail))
    assert DummyForcing.validate_method("fetch_dummy") is False


def test_get_access_function(tmp_path):
    func = ProductRegistry.get_access_function("dummy", "dummy_method")
    func(dates="asdasd", output_folder=tmp_path, output_filename="asdasd")


@pytest.mark.slow
def test_validate_all_registered_access_methods():
    """Exercise validate_function for every registered product/access method.

    This makes a real "toy call" per method (BaseProduct.validate_method), which
    for real products can hit real network APIs or campaign storage — not
    something to run on every user invocation, so it's excluded from the fast
    suite and only run here, deliberately, as a slow test.
    """
    ProductRegistry.load()

    failures = []
    for product_name in ProductRegistry.list_products():
        for method_name in ProductRegistry.list_access_methods(product_name):
            if ProductRegistry.validate_function(product_name, method_name) is False:
                failures.append(f"{product_name}.{method_name}")

    assert not failures, f"validate_method failed for: {failures}"


def test_time_sampling_must_be_declared():
    with pytest.raises(ValueError, match="time_sampling"):

        class Undeclared(DatedBaseProduct):
            product_name = "undeclared_time_sampling"
            description = "d"
            link = "l"


def test_time_sampling_must_be_a_time_sampling():
    with pytest.raises(AssertionError, match="TimeSampling"):

        class Bare(DatedBaseProduct):
            product_name = "bare_time_sampling"
            description = "d"
            link = "l"
            time_sampling = "D"


def test_accessmethod_time_sampling_is_checked_too():
    with pytest.raises(AssertionError, match="TimeSampling"):

        class BadOverride(DatedBaseProduct):
            product_name = "bad_override_time_sampling"
            description = "d"
            link = "l"
            time_sampling = None

            @accessmethod(time_sampling="MS")
            def get(dates, output_folder, output_filename, freq=None):
                pass


def test_user_specified_time_sampling_is_accepted():
    class UserSpecified(DatedBaseProduct):
        product_name = "user_specified_time_sampling"
        description = "d"
        link = "l"
        time_sampling = USER_SPECIFIED

    assert UserSpecified.write_metadata()["time_sampling"] == USER_SPECIFIED


@pytest.mark.parametrize(
    ("frequency", "days"), [("D", 1), ("MS", 31), ("6h", 0.25), ("YS", 366)]
)
def test_max_period_days(frequency, days):
    assert TimeSampling(frequency).max_period_days == days


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency": "not-a-freq"},
        {"frequency": "D", "cell_method": "sum"},
        {"frequency": "D", "anchor": "middle"},
    ],
)
def test_time_sampling_rejects_bad_values(kwargs):
    with pytest.raises(ValueError):
        TimeSampling(**kwargs)


def test_time_sampling_is_written_into_metadata():
    assert DummyForcing.write_metadata()["time_sampling"] == {
        "frequency": "D",
        "cell_method": "mean",
        "anchor": "center",
    }


def test_every_registered_dated_product_declares_time_sampling():
    ProductRegistry.load()
    for product in ProductRegistry.products.values():
        if issubclass(product, DatedBaseProduct):
            assert "time_sampling" in vars(product), product.__name__


class _Sampled(DatedBaseProduct):
    product_name = "sampled_for_freq_tests"
    description = "d"
    link = "l"
    time_sampling = TimeSampling("D")

    @accessmethod(freq_handling="subsample")
    def strided(dates, output_folder, output_filename, freq=None):
        pass

    @accessmethod
    def ranged(dates, output_folder, output_filename, freq=None):
        pass

    @accessmethod(freq_handling="declare")
    def declared(dates, output_folder, output_filename, freq=None):
        pass


def test_freq_must_be_an_optional_argument():
    with pytest.raises(ValueError, match="optional freq"):

        class NoFreq(DatedBaseProduct):
            product_name = "no_freq"
            description = "d"
            link = "l"
            time_sampling = None

            @accessmethod
            def get(dates, output_folder, output_filename):
                pass


def test_resolve_time_sampling_defaults_to_the_declared_one():
    assert resolve_time_sampling(_Sampled, "ranged") == TimeSampling("D")


def test_resolve_time_sampling_subsamples_coarser():
    assert resolve_time_sampling(_Sampled, "strided", "MS").frequency == "MS"


def test_resolve_time_sampling_rejects_finer_than_native():
    with pytest.raises(ValueError, match="finer"):
        resolve_time_sampling(_Sampled, "strided", "6h")


def test_resolve_time_sampling_refuses_freq_a_method_cannot_honour():
    assert resolve_time_sampling(_Sampled, "ranged", "D") == TimeSampling("D")
    with pytest.raises(NotImplementedError, match="cannot sub-sample"):
        resolve_time_sampling(_Sampled, "ranged", "MS")


def test_resolve_time_sampling_declare_takes_freq_as_the_source_cadence():
    assert resolve_time_sampling(_Sampled, "declared", "6h").frequency == "6h"


def test_user_specified_product_needs_freq():
    ProductRegistry.load()
    product = ProductRegistry.get_product("cesm_mom_output")
    method = "get_mom6_single_variable_data"
    with pytest.raises(ValueError, match="function_overrides"):
        resolve_time_sampling(product, method)
    assert resolve_time_sampling(product, method, "D") == TimeSampling("D")


def test_static_product_takes_no_freq():
    ProductRegistry.load()
    product = ProductRegistry.get_product("cice_restart")
    assert resolve_time_sampling(product, "get_cice_restart_subset") is None
    with pytest.raises(ValueError, match="static"):
        resolve_time_sampling(product, "get_cice_restart_subset", "D")


def test_sample_dates_strides_from_the_freq_anchor():
    dates = sample_dates("2020-01-10", "2020-03-05", "MS")
    assert list(dates.strftime("%m-%d")) == ["02-01", "03-01"]


def test_sample_dates_falls_back_to_the_window_start():
    dates = sample_dates("2020-01-10", "2020-01-11", "MS")
    assert list(dates.strftime("%m-%d")) == ["01-10"]
