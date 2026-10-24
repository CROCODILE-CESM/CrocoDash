import pandas as pd
import pytest

from CrocoDash.forcing import time_windows as tw
from CrocoDash.forcing.obc import _make_date_pairs
from CrocoDash.raw_data_access.base import TimeSampling


@pytest.mark.parametrize(
    "frequency, start, first_record",
    [
        ("MS", "2019-12-02", "2019-01-01"),
        ("MS", "2020-02-29", "2019-01-01"),
        # Data that starts on the run's first day, like GLORYS on 1993-01-01.
        ("D", "1993-01-01", "1993-01-01"),
    ],
)
def test_every_regrid_chunk_of_the_boundary_window_holds_a_record(
    frequency, start, first_record
):
    """REGRID fails on a chunk with no record in it (a 30-day chunk of monthly
    data can fall between two), and GET on a day the data doesn't have."""
    sampling = TimeSampling(frequency)
    start = pd.Timestamp(start)
    records = pd.date_range(
        first_record, start + pd.Timedelta(days=450), freq=frequency
    )
    chunks = tw.chunk_days(sampling)
    for end_offset in range(1, 400, 7):
        end = start + pd.Timedelta(days=end_offset)
        lo, hi = tw.obc_window(sampling, start, end, (records[0], records[-1]))
        assert records[0] <= lo and hi <= records[-1]
        for a, b in _make_date_pairs(
            lo, hi, chunks["regrid_step_days"], chunks["min_chunk_days"]
        ):
            assert ((records >= a) & (records <= b)).any(), (a, b)
