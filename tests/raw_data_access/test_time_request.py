import cftime
import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.raw_data_access.time_request import TimeRequest


def test_thinning_stays_on_the_window_dates_across_get_chunks():
    """Each 7-day GET chunk used to thin from its own first day, so 5D came
    out 5, 2, 5, 2 days apart. The chunks of one request keep its dates, and
    each date keeps the record whose time bounds hold it, even for a mean
    stamped mid-interval (MOM6), whose nearest record can be the month
    before."""
    when = TimeRequest.every("5D", "2020-01-01", "2020-01-14")
    days = [
        day
        for start, end in [("2020-01-01", "2020-01-07"), ("2020-01-08", "2020-01-14")]
        for day in when.between(start, end).days()
    ]
    assert days == list(pd.date_range("2020-01-01", periods=3, freq="5D"))

    lo = [cftime.datetime(2000, m, 1, calendar="noleap") for m in range(1, 13)]
    hi = lo[1:] + [cftime.datetime(2001, 1, 1, calendar="noleap")]
    ds = xr.Dataset(
        {"time_bnds": (("time", "nv"), np.stack([lo, hi], axis=1))},
        coords={
            "time": (
                "time",
                [a + (b - a) / 2 for a, b in zip(lo, hi)],
                {"bounds": "time_bnds"},
            )
        },
    )
    when = TimeRequest.every("QS", "2000-01-01", "2000-12-31")
    months = [
        t.month
        for start, end in [("2000-01-01", "2000-06-30"), ("2000-07-01", "2000-12-31")]
        for t in when.between(start, end).select(ds).time.values
    ]
    assert months == [1, 4, 7, 10]
