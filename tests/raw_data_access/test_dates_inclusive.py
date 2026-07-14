"""Enforce that every DatedBaseProduct access method handles an inclusive
end-of-day date range — without paying any cost at runtime.

Classes get this kind of enforcement for free from __init_subclass__ (it can
check required args/metadata once, at import time). Individual access-method
*functions* can't be enforced that way, since what matters is runtime
behavior, not shape — and adding a live validation wrapper to every call
either does nothing (raw date strings only, e.g. RDA reparsing via
pd.date_range) or is only checkable with real network credentials (CDS API).
So this test is a structural check instead: it discovers every registered
DatedBaseProduct access method and confirms it routes its `dates` argument
through raw_data_access.datasets.utils.make_dates_end_inclusive, unless it's
explicitly allowlisted as already inclusive by construction.

This is exactly the bug class that motivated this file: GLORYS's CDS API path
used to pass `dates[-1]` straight through as `end_datetime`, silently
truncating every chunk to midnight and dropping the last day.
"""

import inspect

from CrocoDash.raw_data_access.base import DatedBaseProduct
from CrocoDash.raw_data_access.datasets.utils import make_dates_end_inclusive
from CrocoDash.raw_data_access.registry import ProductRegistry

# (product_name, method_name) pairs allowed to skip make_dates_end_inclusive.
KNOWN_INCLUSIVE_WITHOUT_HELPER = {
    # Reparses `dates` via pd.date_range(freq="D"), which is whole-day
    # inclusive regardless of time-of-day — nothing to normalize.
    ("glorys", "get_glorys_data_from_rda"),
    ("glofas", "get_global_data_with_python"),
    ("mom6_output", "get_mom6_data"),
    # `dates` is an unused placeholder — downloads one fixed pre-processed
    # file via a static URL, no date-based filtering happens at all.
    ("glofas", "get_processed_global_glofas_script_for_cli"),
    # Test fixtures from test_base_registry.py — placeholder data, not real
    # date handling.
    ("dummy", "dummy_method"),
    ("dummy_forcing", "fetch_dummy"),
}


def _source_of(product_name: str, method_name: str) -> str:
    func = ProductRegistry.get_access_function(product_name, method_name)
    func = getattr(func, "__func__", func)
    return inspect.getsource(func)


def test_dated_access_methods_handle_inclusive_end_dates():
    ProductRegistry.load()

    unchecked = []
    for product_name in ProductRegistry.list_products():
        product = ProductRegistry.get_product(product_name)
        if not issubclass(product, DatedBaseProduct):
            continue
        for method_name in ProductRegistry.list_access_methods(product_name):
            if (product_name, method_name) in KNOWN_INCLUSIVE_WITHOUT_HELPER:
                continue
            if make_dates_end_inclusive.__name__ not in _source_of(
                product_name, method_name
            ):
                unchecked.append(f"{product_name}.{method_name}")

    assert not unchecked, (
        "These DatedBaseProduct access methods don't call "
        "make_dates_end_inclusive and aren't in KNOWN_INCLUSIVE_WITHOUT_HELPER "
        "— verify they handle an inclusive end-of-day date range, then either "
        f"use the helper or extend the allowlist with a reason: {unchecked}"
    )


def test_make_dates_end_inclusive():
    start, end = make_dates_end_inclusive(["2020-01-01", "2020-01-31"])
    assert start == "2020-01-01 00:00:00"
    assert end == "2020-01-31 23:59:59"


def test_make_dates_end_inclusive_single_day():
    start, end = make_dates_end_inclusive(["2020-01-01", "2020-01-01"])
    assert start == "2020-01-01 00:00:00"
    assert end == "2020-01-01 23:59:59"
