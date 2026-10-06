from datetime import datetime

import pandas as pd
import pytest

from CrocoDash.forcing import time_windows as tw
from CrocoDash.forcing.obc import _make_date_pairs
from CrocoDash.raw_data_access.base import TimeSampling

DAILY = TimeSampling("D")
MONTHLY = TimeSampling("MS", "mean", "end")
START, END = datetime(2020, 1, 10), datetime(2020, 1, 20)


def test_daily_data_keeps_the_original_chunking_and_is_padded_a_day():
    assert tw.chunk_days(DAILY) == {
        "get_step_days": 7,
        "regrid_step_days": 30,
        "min_chunk_days": 1,
    }
    assert tw.obc_window(DAILY, START, END) == (
        datetime(2020, 1, 9),
        datetime(2020, 1, 21),
    )
    assert tw.ic_lookback_days(DAILY) == 0


def test_monthly_data_gets_chunks_and_windows_of_whole_records():
    assert tw.chunk_days(MONTHLY) == {
        "get_step_days": 31,
        "regrid_step_days": 62,
        "min_chunk_days": 31,
    }
    assert tw.obc_window(MONTHLY, START, END) == (
        datetime(2019, 12, 10),
        datetime(2020, 2, 20),
    )
    assert tw.ic_lookback_days(MONTHLY) == 30


def test_a_short_trailing_chunk_joins_the_one_before():
    pairs = _make_date_pairs(datetime(2020, 1, 1), datetime(2020, 3, 5), 62, 31)
    assert pairs == [(datetime(2020, 1, 1), datetime(2020, 3, 5))]


@pytest.mark.parametrize("start", ["2019-12-02", "2020-01-17", "2020-02-29"])
def test_every_monthly_regrid_chunk_holds_a_record(start):
    records = pd.date_range("2019-01-01", "2022-01-01", freq="MS")
    start = pd.Timestamp(start).to_pydatetime()
    chunks = tw.chunk_days(MONTHLY)
    for end_offset in range(1, 400, 7):
        end = start + pd.Timedelta(days=end_offset)
        for lo, hi in _make_date_pairs(
            start, end, chunks["regrid_step_days"], chunks["min_chunk_days"]
        ):
            if (hi - lo).days + 1 >= chunks["min_chunk_days"]:
                assert ((records >= lo) & (records <= hi)).any(), (lo, hi)


def test_describe_warns_about_a_run_shorter_than_one_record():
    lines = tw.describe(
        "cesm_pop_output",
        "get",
        MONTHLY,
        MONTHLY,
        None,
        START,
        END,
        tw.chunk_days(MONTHLY),
    )
    assert "2019-12-10 → 2020-02-20" in lines[1]
    assert any("shorter than one MS record spacing" in line for line in lines)


def test_describe_warns_that_subsampled_means_are_not_interval_means():
    sampled = TimeSampling("MS")
    lines = tw.describe(
        "glorys", "get", sampled, DAILY, "MS", START, END, tw.chunk_days(sampled)
    )
    assert any("not a mean over the MS interval" in line for line in lines)
    assert not any(
        "[warn]" in line
        for line in tw.describe(
            "glorys", "get", DAILY, DAILY, None, START, END, tw.chunk_days(DAILY)
        )
    )
