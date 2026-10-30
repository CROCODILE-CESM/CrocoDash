import numpy as np
import xarray as xr

from CrocoDash.raw_data_access.region import Region


def test_select_crosses_the_source_seam_in_order():
    """The source's longitudes start at 250E and wrap round, its last column
    repeating its first. A box across either of its seams comes back west to
    east, each column once, with the data that belongs to each label, and a
    full circle gives every column once."""
    lon = np.append(np.arange(250.0, 610.0) % 360, 250.0)
    ds = xr.Dataset(
        {"v": (("lat", "lon"), np.tile(lon, (2, 1)))},
        coords={"lat": [0.0, 1.0], "lon": lon},
    )
    for box, expected in [
        (Region(0, 1, 240, 260), np.arange(-120.0, -99.0)),  # on [-180, 180)
        (Region(0, 1, -10, 10), np.arange(-10.0, 11.0)),
        (Region(-90, 90, -180, 180), np.arange(-180.0, 180.0)),
    ]:
        out = box.select(ds)
        np.testing.assert_array_equal(out.lon, expected)
        np.testing.assert_array_equal(out.v % 360, np.tile(expected % 360, (2, 1)))

    # On a 2-D (curvilinear) source a full circle also starts at its west edge.
    lon2 = np.tile(lon[:-1], (2, 1))
    ds2 = xr.Dataset(
        {"v": (("y", "x"), lon2)},
        coords={
            "lon": (("y", "x"), lon2),
            "lat": (("y", "x"), 0 * lon2 + [[0.0], [1.0]]),
        },
    )
    out = Region(-90, 90, -180, 180).select(ds2)
    np.testing.assert_array_equal(out.lon[0], np.arange(-180.0, 180.0))
    np.testing.assert_array_equal(out.v[0] % 360, np.arange(-180.0, 180.0) % 360)
