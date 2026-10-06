"""Size forcing requests to the time sampling of the product they read.

Every product used to get the same 7-day GET and 30-day REGRID chunks. That
suits daily data, but a 30-day REGRID chunk of monthly data can fall between
two records and come out empty. These keep those targets for daily and finer
data and grow them for coarser data, so every chunk holds at least one record.
"""

from datetime import timedelta
from math import ceil

from CrocoDash.raw_data_access.base import TimeSampling, resolve_time_sampling

# GET and REGRID chunk sizes are independent, and neither changes the result
# -- a 1-day and a 3-day chunking of the same range were verified to produce
# bit-identical forcing files. They only set how much concurrency obc.py's
# pools have to work with.
#
# GET is network-bound, so it wants more chunks than REGRID: at a 30-day step
# anything shorter than a month came out as a single chunk and downloaded
# serially. A week gives a fortnight-long case two concurrent fetches and a
# year fifty-odd, without splitting long runs into thousands of requests.
#
# REGRID stays at 30 days. Its per-chunk cost is real work rather than
# waiting, so slicing it finer mostly buys more chunk files to merge.
GET_TARGET_DAYS = 7
REGRID_TARGET_DAYS = 30


def native_sampling(product, function_name, freq):
    """The sampling of the source itself: freq names it for a method that takes
    freq as the source's cadence, but only thins it for a sub-sampling one."""
    method = product._access_methods[function_name]
    if getattr(method, "_freq_handling", None) == "subsample":
        freq = None
    return resolve_time_sampling(product, function_name, freq)


def period_days(ts: TimeSampling) -> int:
    """Longest gap between records, in whole days (at least one)."""
    return max(1, ceil(ts.max_period_days))


def chunk_days(ts: TimeSampling) -> dict:
    """GET/REGRID chunk sizes, and the shortest chunk allowed: one record
    spacing, so every chunk holds a record. REGRID gets two spacings, so a
    chunk can interpolate between records."""
    period = period_days(ts)
    return {
        "get_step_days": max(GET_TARGET_DAYS, period),
        "regrid_step_days": max(REGRID_TARGET_DAYS, 2 * period),
        "min_chunk_days": period,
    }


def obc_window(ts: TimeSampling, start, end):
    """The date range to fetch boundary data for: data coarser than daily is
    padded by one record spacing each side, so its records bracket the run."""
    pad = timedelta(days=period_days(ts) if ts.max_period_days > 1 else 0)
    return start - pad, end + pad


def ic_lookback_days(ts: TimeSampling) -> int:
    """Days before the start the IC request reaches back, so a window of one
    record spacing ending at the start always holds the record at or before it."""
    return period_days(ts) - 1


def describe(product_name, function_name, ts, native, freq, start, end, chunks):
    """Lines telling the user what their request means for this product."""
    obc_start, obc_end = obc_window(ts, start, end)
    run_days = (end - start).days + 1
    lines = [
        f"[info] Conditions forcing from {product_name}.{function_name}: "
        f"{ts.describe()}.",
        f"[info] Run {start:%Y-%m-%d} → {end:%Y-%m-%d} ({run_days} days); boundary "
        f"data fetched for {obc_start:%Y-%m-%d} → {obc_end:%Y-%m-%d} in "
        f"{chunks['get_step_days']}-day GET and {chunks['regrid_step_days']}-day "
        "REGRID chunks.",
    ]
    if run_days < ts.max_period_days:
        lines.append(
            f"[warn] The run is shorter than one {ts.frequency} record spacing, so "
            "its boundary data is just the records either side of it."
        )
    if freq is not None and ts != native and native.cell_method == "mean":
        lines.append(
            f"[warn] freq={freq!r} sub-samples {native.frequency} means: each record "
            f"is a single {native.frequency} mean, not a mean over the {freq} "
            "interval."
        )
    return lines
