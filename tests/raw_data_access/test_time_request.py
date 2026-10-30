import pandas as pd

from CrocoDash.raw_data_access.time_request import TimeRequest


def test_thinning_stays_on_the_window_dates_across_get_chunks():
    """Each 7-day GET chunk used to thin from its own first day, so 5D came
    out 5, 2, 5, 2 days apart. The chunks of one request keep its dates."""
    when = TimeRequest.every("5D", "2020-01-01", "2020-01-14")
    days = [
        day
        for start, end in [("2020-01-01", "2020-01-07"), ("2020-01-08", "2020-01-14")]
        for day in when.between(start, end).days()
    ]
    assert days == list(pd.date_range("2020-01-01", periods=3, freq="5D"))
