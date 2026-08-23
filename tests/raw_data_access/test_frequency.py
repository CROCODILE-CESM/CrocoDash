"""The frequency contract for dated products.

Two halves, and they enforce different things:

1. *Shape*, at import time. Every DatedBaseProduct declares a
   ``native_frequency`` and every one of its access methods takes an optional
   ``freq``. __init_subclass__ enforces this, so a product that forgets either
   one cannot be defined at all -- the tests below assert the failure modes
   rather than waiting for a process_forcings run to hit them.

2. *Behavior*, at call time. Declaring ``freq`` says nothing about honouring a
   given value: an access method that fetches by date range (a server-side
   query, a generated script, a file-window overlap scan) has nothing to stride.
   Those raise NotImplementedError instead of accepting the argument and
   silently ignoring it, which would be the one genuinely bad outcome.
"""

import inspect

import pytest

from CrocoDash.raw_data_access.base import (
    DatedBaseProduct,
    MOM6ForcingProduct,
    accessmethod,
    frequency_step,
    require_native_frequency,
    resolve_frequency,
)
from CrocoDash.raw_data_access.registry import ProductRegistry

# --- 1. Shape: enforced at class-creation time ---------------------------


def test_missing_freq_arg_is_rejected():
    with pytest.raises(ValueError, match="missing tunable arg 'freq'"):

        class NoFreq(DatedBaseProduct):
            product_name = "no_freq"
            description = "Access method omits freq entirely"
            link = "n/a"
            native_frequency = "D"

            @accessmethod
            def fetch(dates, output_folder, output_filename):
                return None


def test_required_positional_freq_arg_is_rejected():
    # A freq without a default would break every ordinary call: the framework
    # only passes freq when the user overrides it, so the call would raise
    # TypeError on the missing positional argument.
    with pytest.raises(ValueError, match="without a default"):

        class PositionalFreq(DatedBaseProduct):
            product_name = "positional_freq"
            description = "Access method makes freq required"
            link = "n/a"
            native_frequency = "D"

            @accessmethod
            def fetch(dates, output_folder, output_filename, freq):
                return None


def test_missing_native_frequency_is_rejected():
    with pytest.raises(ValueError, match="missing required metadata: native_frequency"):

        class NoCadence(DatedBaseProduct):
            product_name = "no_cadence"
            description = "Product never declares its cadence"
            link = "n/a"

            @accessmethod
            def fetch(dates, output_folder, output_filename, freq=None):
                return None


def test_native_frequency_may_be_none_but_must_be_declared():
    # None is a meaningful declaration -- "cadence depends on the archive the
    # user points at" -- as opposed to simply not having thought about it.
    class ArchiveDependent(DatedBaseProduct):
        product_name = "archive_dependent_cadence"
        description = "Cadence comes from the data, not the product"
        link = "n/a"
        native_frequency = None

        @accessmethod
        def fetch(dates, output_folder, output_filename, freq=None):
            return None

    assert ArchiveDependent.native_frequency is None


def test_every_registered_dated_method_accepts_optional_freq():
    """Structural sweep over the real products, mirroring test_dates_inclusive.

    Catches a product added without going through DatedBaseProduct's enforcement
    (e.g. one registered by hand).
    """
    ProductRegistry.load()

    offenders = []
    for product_name in ProductRegistry.list_products():
        product = ProductRegistry.get_product(product_name)
        if not issubclass(product, DatedBaseProduct):
            continue
        assert hasattr(product, "native_frequency"), product_name
        for method_name in ProductRegistry.list_access_methods(product_name):
            func = ProductRegistry.get_access_function(product_name, method_name)
            param = inspect.signature(getattr(func, "__func__", func)).parameters.get(
                "freq"
            )
            if param is None or param.default is inspect._empty:
                offenders.append(f"{product_name}.{method_name}")

    assert not offenders, (
        "These dated access methods don't accept an optional freq: "
        f"{offenders}. Every dated method must, so that a single "
        'function_overrides={"freq": ...} is valid whichever method is chosen.'
    )


# --- 2. Behavior: frequency arithmetic and validation --------------------


@pytest.mark.parametrize(
    "coarse, fine",
    [
        ("MS", "D"),
        ("D", "6h"),
        ("YS", "MS"),
        ("W", "D"),
        ("3D", "D"),
    ],
)
def test_frequency_step_orders_calendar_and_fixed_aliases(coarse, fine):
    # Calendar offsets like MS have no fixed duration, so to_offset(...).nanos
    # raises on them; frequency_step has to handle both kinds uniformly.
    assert frequency_step(coarse) > frequency_step(fine)


def test_frequency_step_rejects_garbage():
    with pytest.raises(ValueError, match="not a valid pandas frequency alias"):
        frequency_step("not-a-freq")


class _Daily:
    product_name = "daily_thing"
    native_frequency = "D"


class _ArchiveDependent:
    product_name = "archive_thing"
    native_frequency = None


def test_resolve_frequency_defaults_to_native():
    # freq=None must be a no-op, so existing call sites keep their behavior.
    assert resolve_frequency(_Daily, None) == "D"


def test_resolve_frequency_allows_coarser_and_equal():
    assert resolve_frequency(_Daily, "MS") == "MS"
    assert resolve_frequency(_Daily, "D") == "D"


def test_resolve_frequency_rejects_finer_than_native():
    # Sampling daily data hourly would silently return 1/24 of the requested
    # stamps rather than failing.
    with pytest.raises(ValueError, match="finer than"):
        resolve_frequency(_Daily, "6h")


def test_resolve_frequency_passes_through_when_cadence_unknown():
    assert resolve_frequency(_ArchiveDependent, "MS") == "MS"
    assert resolve_frequency(_ArchiveDependent, None) is None


def test_require_native_frequency_accepts_none_and_native():
    assert require_native_frequency(_Daily, None, "m", "hint") is None
    assert require_native_frequency(_Daily, "D", "m", "hint") is None


def test_require_native_frequency_rejects_anything_else():
    with pytest.raises(NotImplementedError, match="cannot sub-sample"):
        require_native_frequency(_Daily, "MS", "m", "some reason.")


# --- 3. The real products' declared positions ---------------------------


@pytest.mark.parametrize(
    "product_name, expected",
    [
        ("glorys", "D"),
        ("glofas", "D"),
        ("reference_ocean", "D"),
        # Cadence follows dataset_path (.../month_1 vs day_1), not the product.
        ("cesm_pop_output", None),
        ("cesm_mom_output", None),
    ],
)
def test_declared_native_frequencies(product_name, expected):
    ProductRegistry.load()
    assert ProductRegistry.get_product(product_name).native_frequency == expected


@pytest.mark.parametrize(
    "product_name, method_name",
    [
        # Server-side range query; no stride to ask for.
        ("glorys", "get_glorys_data_from_cds_api"),
        ("glorys", "get_glorys_data_script_for_cli"),
        # Whole-file selection by date-range overlap; every native record kept.
        ("cesm_pop_output", "get_cesm_single_variable_data"),
        ("cesm_mom_output", "get_mom6_single_variable_data"),
        ("cesm_mom_output", "get_mom6_output_data"),
        # Fetches one fixed pre-processed file; ignores dates entirely.
        ("glofas", "get_processed_global_glofas_script_for_cli"),
    ],
)
def test_methods_that_cannot_subsample_say_so(product_name, method_name, tmp_path):
    """The important half: a method that can't honour freq must refuse it.

    Accepting freq and quietly ignoring it would hand back a full-cadence
    download while the config records a coarse one -- the failure mode this
    whole contract exists to prevent. Asserted before any I/O happens, so no
    credentials or archive access are needed.
    """
    ProductRegistry.load()
    func = ProductRegistry.get_access_function(product_name, method_name)
    # Supply only the args this method actually declares -- the guard fires
    # before any of them are used, so the values just need to be well-typed.
    params = inspect.signature(getattr(func, "__func__", func)).parameters
    candidates = {
        "dates": ["2020-01-01", "2020-01-31"],
        "lat_min": 30.0,
        "lat_max": 31.0,
        "lon_min": -60.0,
        "lon_max": -59.0,
        "output_folder": tmp_path,
        "output_filename": "unused.nc",
        "freq": "MS",
    }
    with pytest.raises(NotImplementedError, match="cannot sub-sample"):
        func(**{k: v for k, v in candidates.items() if k in params})


def test_reference_ocean_honours_freq_end_to_end(tmp_path):
    """REFERENCE_OCEAN generates its own time axis, so it needs no archive."""
    from CrocoDash.raw_data_access.datasets.reference import REFERENCE_OCEAN
    import xarray as xr

    common = dict(
        dates=["2020-01-01", "2020-12-31"],
        lat_min=30.0,
        lat_max=31.0,
        lon_min=-60.0,
        lon_max=-59.0,
        output_folder=tmp_path,
    )
    REFERENCE_OCEAN.get_reference_ocean_data(
        **common, output_filename="daily.nc", freq=None
    )
    REFERENCE_OCEAN.get_reference_ocean_data(
        **common, output_filename="monthly.nc", freq="MS"
    )

    with xr.open_dataset(tmp_path / "daily.nc") as daily, xr.open_dataset(
        tmp_path / "monthly.nc"
    ) as monthly:
        assert daily.sizes["time"] == 366  # 2020 is a leap year
        assert monthly.sizes["time"] == 12


def test_reference_ocean_rejects_finer_than_daily(tmp_path):
    from CrocoDash.raw_data_access.datasets.reference import REFERENCE_OCEAN

    with pytest.raises(ValueError, match="finer than"):
        REFERENCE_OCEAN.get_reference_ocean_data(
            dates=["2020-01-01", "2020-01-02"],
            lat_min=30.0,
            lat_max=31.0,
            lon_min=-60.0,
            lon_max=-59.0,
            output_folder=tmp_path,
            output_filename="hourly.nc",
            freq="6h",
        )
