"""The box a dated access call fetches.

The caller builds one Region for each box it needs (an OBC edge, the whole
domain) and hands it to the access method, which @accessmethod pads once by
the product's buffer. Readers cut their files with select, and remote APIs
that can't take a range across their own seam take lon_ranges.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Region:
    """A lat/lon box to fetch. Longitudes run east from lon_min to lon_max, so a box
    across 180E is 170..190, and a 360-wide box is every longitude."""

    lat_min: float
    lat_max: float
    lon_min: float  # put on [-180, 180); lon_max moves with it
    lon_max: float  # lon_min <= lon_max <= lon_min + 360, else ValueError

    def __post_init__(self):
        lat_min, lat_max, lon_min, lon_max = map(
            float, (self.lat_min, self.lat_max, self.lon_min, self.lon_max)
        )
        if lat_max < lat_min:
            raise ValueError(f"lat_max {lat_max} is below lat_min {lat_min}.")
        if not lon_min <= lon_max <= lon_min + 360:
            raise ValueError(
                f"lon_min {lon_min} and lon_max {lon_max} are not a box: lon_max "
                "runs east of lon_min by at most 360, so for a box across 180E "
                "give lon_max past 180, e.g. 170..190."
            )
        turns = np.floor((lon_min + 180) / 360) * 360
        for name, value in zip(
            ("lat_min", "lat_max", "lon_min", "lon_max"),
            (lat_min, lat_max, lon_min - turns, lon_max - turns),
        ):
            object.__setattr__(self, name, float(value))

    @classmethod
    def around(cls, lon, lat) -> "Region":
        """The smallest box holding these points (any shape), going the short
        way round."""
        lon = np.unique(np.mod(np.ravel(lon), 360))
        lat = np.ravel(lat)
        # The box leaves out the widest gap between neighbouring longitudes.
        gaps = np.diff(lon, append=lon[0] + 360)
        widest = np.argmax(gaps)
        west = lon[(widest + 1) % lon.size]
        return cls(lat.min(), lat.max(), west, west + 360 - gaps[widest])

    def padded(self, deg) -> "Region":
        """Grown by deg on every side; latitudes stop at +-90, the width at 360."""
        middle = (self.lon_min + self.lon_max) / 2
        half = min(self.lon_max - self.lon_min + 2 * deg, 360) / 2
        return Region(
            max(self.lat_min - deg, -90),
            min(self.lat_max + deg, 90),
            middle - half,
            middle + half,
        )

    def select(self, ds, lon="lon", lat="lat"):
        """ds cut to the box by index. 1-D or 2-D lon/lat. Columns come west to
        east across the source's own seam, each once, and longitudes are
        relabelled onto lon_min..lon_min+360. On a 2-D source where the box's
        cells fall in more than one column run (a tripole fold), every column
        of those rows is kept. ValueError if no cell is in the box."""
        lons, lats = ds[lon], ds[lat].values
        east = (lons.values - self.lon_min) % 360 + self.lon_min
        in_lat = (lats >= self.lat_min) & (lats <= self.lat_max)
        in_lon = east <= self.lon_max
        if lons.ndim == 1:
            (y,), (x,) = ds[lat].dims, lons.dims
            rows, cols = np.flatnonzero(in_lat), np.flatnonzero(in_lon)
            # West to east, and a column the source repeats (0 and 360) once.
            cols = cols[np.unique(east[cols], return_index=True)[1]]
        else:
            y, x = lons.dims
            cells = in_lat & in_lon
            rows = np.flatnonzero(cells.any(axis=1))
            cols = np.flatnonzero(cells.any(axis=0))
            if cols.size:
                rows = np.arange(rows[0], rows[-1] + 1)
                runs = np.flatnonzero(np.diff(cols, append=cols[0] + lons.shape[1]) > 1)
                # One run of columns, started past the source's seam if it
                # crosses it. Every column when all are in, or when the cells
                # fall in more than one run (a tripole fold).
                if runs.size == 1:
                    cols = np.roll(cols, -(runs[0] + 1))
                else:
                    cols = np.arange(lons.shape[1])
        if not (rows.size and cols.size):
            raise ValueError(
                f"No cell of the data is in {self}: its {lat} runs "
                f"{np.nanmin(lats):g}..{np.nanmax(lats):g}. Ask for a box the "
                "data covers."
            )
        out = ds.isel({y: rows, x: cols})
        out[lon] = out[lon].copy(
            data=(out[lon].values - self.lon_min) % 360 + self.lon_min
        )
        return out

    def lon_ranges(self, west=-180) -> list[tuple[float, float]]:
        """The box's longitudes as one or two ranges inside [west, west + 360),
        for remote APIs that can't take a range across their own seam."""
        west, width = float(west), self.lon_max - self.lon_min
        if width >= 360:
            return [(west, west + 360)]
        start = (self.lon_min - west) % 360 + west
        if start + width <= west + 360:
            return [(start, start + width)]
        return [(start, west + 360), (west, start + width - 360)]
