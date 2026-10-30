"""The records a dated access call asks for.

The caller builds one TimeRequest for a whole window and hands each chunk of
it to the access method, so thinning works out the same dates however the
window is cut, and the method keeps the records it is asked for with select,
whatever calendar its data is in.
"""

from dataclasses import dataclass, replace

import cftime
import pandas as pd

_DAY = pd.Timedelta(days=1)


@dataclass(frozen=True)
class TimeRequest:
    """The records to fetch: every record from start to end, both days included, or,
    with dates, only the record nearest each of those dates."""

    start: pd.Timestamp
    end: pd.Timestamp
    dates: tuple[pd.Timestamp, ...] | None = None  # thinned; None keeps every record

    def __post_init__(self):
        # Whole days: any date-like is accepted and kept at midnight.
        start, end = (pd.Timestamp(t).normalize() for t in (self.start, self.end))
        if end < start:
            raise ValueError(
                f"The request ends {end:%Y-%m-%d}, before it starts {start:%Y-%m-%d}."
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        if self.dates is not None:
            object.__setattr__(self, "dates", tuple(map(pd.Timestamp, self.dates)))

    @classmethod
    def every(cls, freq, start, end) -> "TimeRequest":
        """One date per freq from start to end, worked out once for the whole
        window, so every chunk of it thins on the same dates. freq comes from
        configure, where resolve_time_sampling already checked it is coarser
        than the data."""
        window = cls(start, end)
        return replace(
            window, dates=tuple(pd.date_range(window.start, window.end, freq=freq))
        )

    def between(self, start, end) -> "TimeRequest":
        """One chunk of this request, keeping only its dates that fall inside."""
        chunk = TimeRequest(start, end)
        if self.dates is None:
            return chunk
        return replace(
            chunk,
            dates=tuple(d for d in self.dates if chunk.start <= d < chunk.end + _DAY),
        )

    def days(self) -> list[pd.Timestamp]:
        """The days to read: the thinned dates, or every day start..end."""
        if self.dates is not None:
            return list(self.dates)
        return list(pd.date_range(self.start, self.end, freq="D"))

    def select(self, ds, time="time"):
        """The records of ds this request asks for, in ds's own calendar
        (cftime and noleap included; a Feb 29 date becomes Mar 1 there):
        those from start to the end of the end day, then, with dates, the
        nearest record to each date, each once. ValueError naming the window
        if none is left."""
        times = ds[time].values
        keep = []
        if len(times):
            lo, hi = (_like(t, times[0]) for t in (self.start, self.end + _DAY))
            keep = [i for i, t in enumerate(times) if lo <= t < hi]
        if keep and self.dates is not None:
            # A tie goes to the later record: for means stamped mid-interval
            # (a daily mean at noon), that is the one whose interval holds
            # the date.
            keep = sorted(
                {
                    min(keep, key=lambda i: (abs(times[i] - d), -i))
                    for d in (_like(d, times[0]) for d in self.dates)
                }
            )
        if not keep:
            held = (
                f"; the data runs {str(times[0])[:10]} → {str(times[-1])[:10]}"
                if len(times)
                else ""
            )
            raise ValueError(
                f"No records between {self.start:%Y-%m-%d} and {self.end:%Y-%m-%d}"
                f"{held}."
            )
        return ds.isel({time: keep})


def _like(ts, record):
    """ts as a value comparable with record, a time from the data: a cftime
    date in its calendar, where a day the calendar lacks (Feb 29 in noleap)
    becomes the first of the next month, or a numpy datetime64."""
    if not isinstance(record, cftime.datetime):
        return ts.to_datetime64()
    try:
        return cftime.datetime(*ts.timetuple()[:6], calendar=record.calendar)
    except ValueError:
        year, month = divmod(ts.year * 12 + ts.month, 12)
        return cftime.datetime(year, month + 1, 1, calendar=record.calendar)
