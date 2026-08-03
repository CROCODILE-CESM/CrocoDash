"""
Data Access Module -> WW3 (placeholder)

WW3 boundary-spectra sourcing (e.g. real ERA5 2D wave spectra, or a parent
CESM/WW3 run's own point output) isn't wired up yet. This access method
writes a trivial time-only raw file for the requested date range/bounding
box -- just enough to satisfy obc.py's GET-step contract -- so
extract_forcings/ww3.py can drive its own constant-value-spectrum regrid
step through the shared GET -> chunk -> REGRID -> MERGE engine instead of
standing alone.
"""

from pathlib import Path

import numpy as np
import xarray as xr

from CrocoDash.raw_data_access.base import *


class WW3(WW3ForcingProduct):
    product_name = "ww3"
    description = (
        "Placeholder WW3 boundary-spectra product -- writes a time-only raw "
        "file; no real wave data yet."
    )
    link = "https://github.com/CROCODILE-CESM/WW3_interface"
    time_var_name = "time"
    # Matches extract_forcings/ww3.py's own regrid-step time encoding.
    time_units = "seconds since 1990-01-01 00:00:00.0"
    calendar = GREGORIAN

    @accessmethod(
        description="Writes a placeholder time-only raw file for the requested date range",
        type="python",
    )
    def get_ww3_placeholder_data(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="raw_ww3.nc",
        variables=None,
    ):
        # dates carries sub-day precision by design here (unlike day-granularity
        # products like GLORYS) -- see KNOWN_INCLUSIVE_WITHOUT_HELPER in
        # test_dates_inclusive.py for why make_dates_end_inclusive's whole-day
        # normalization doesn't apply.
        start, end = (np.datetime64(d) for d in dates)
        time = np.arange(start, end + np.timedelta64(1, "h"), np.timedelta64(1, "h"))
        ds = xr.Dataset(coords={"time": time})

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(output_folder / output_filename)
