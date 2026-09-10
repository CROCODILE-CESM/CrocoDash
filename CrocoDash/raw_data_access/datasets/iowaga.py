"""
Data Access Module -> IOWAGA WAVEWATCH-III hindcast 2D wave spectra, via OPeNDAP

Fetches Ifremer's IOWAGA global wave hindcast through the THREDDS OPeNDAP
service and reconstructs a 2D spectrum E(f, theta) for use as WW3 boundary
forcing.

Why OPeNDAP rather than the file server
---------------------------------------
The obvious alternative is the plain HTTPS file tree at
`data-dataref.ifremer.fr/ww3/`, which serves whole monthly global files. Those
are ~2.8 GB per month for the field data alone, and a regional boundary strip
needs a vanishingly small corner of each. OPeNDAP subsets **server-side**: the
`.sel()` calls below are translated into a byte-range request for just the
requested time/lat/lon window, so a month of a small domain is megabytes
rather than gigabytes and needs no local scratch staging at all.

READ THIS BEFORE USING: which hindcast this actually is
-------------------------------------------------------
Ifremer publishes several IOWAGA hindcasts and the OPeNDAP service does NOT
serve the newest one. Verified against the live catalogue on 2026-09-10:

  * This module's default, `IOWAGA-GLOBAL_ECMWF-WW3-HINDCAST_FULL_TIME_SERIE`
    on tds3: WW3 v6.07, BETAMAX 1.5, ECMWF operational analysis winds,
    **1991-07-01 to 2019-12-31**, 0.5 degree global.

  * `GLOBMULTI_ERA5_GLOBCUR_01` (the dataset with the Sextant DOI, Alday et
    al. 2021 physics, WW3 v7.08, ERA5 winds + CMEMS-GLOBCURRENT currents,
    1993-2024): **not on OPeNDAP at all**, only on the `data-dataref` file
    tree. Its THREDDS directory exists but is empty apart from a staging
    folder literally named `toremove/`.

And the record is shorter than advertised. The aggregation claims data to
2019-12-31, but its time axis is corrupt from 2018 onward: 46752 steps for
only 40912 unique timestamps, with 24 backward jumps at month boundaries, so
each 2018-2019 month appears about twice and out of order. Only the strictly
increasing prefix -- **1991-07-01 to 2018-01-31** -- is usable, and that is
what `check_coverage` enforces. See DEFAULT_DATASET_COVERAGE.

So this module trades newer physics and a longer record for server-side
subsetting. If you need dates past 2018-01, ERA5 forcing, or the Alday et al.
(2021) parameterization, this product cannot give them to you -- use the file
server instead. `check_coverage` refuses an out-of-range request rather than
silently returning a short or duplicated record.

The catalogue's own `<variables>` block is unreliable: it advertises the
partition fields (phs0-5, ptp0-5, pdir0-5, pspr0-5) which the aggregation
does NOT contain. It appears to be the union over the whole product family.
Everything below resolves variables against the live dataset, never the
catalogue.

How the 2D spectrum is built
----------------------------
The aggregation carries the **observed 1D frequency spectrum** `ef`, on 32
native WW3 frequency bins, plus a frequency-integrated mean direction `dir`
and directional spread `spr`. So:

    E(f, theta) = E(f) * D(theta; dir, spr)

with D a cosine-2s lobe normalized to integrate to 1 over direction in
radians, which makes Hs exactly conservative by construction.

Compared to a fully parametric reconstruction from bulk statistics, the
frequency shape here is **observed, not assumed** -- a real gain. What is
given up is frequency-dependent direction: `dir` and `spr` are single
frequency-integrated values, so every frequency band is assigned the same
mean direction and the same spread. A crossing sea (wind sea from one
direction, swell from another) therefore collapses onto one smeared lobe
rather than showing two. For a boundary condition dominated by a single
swell system this is minor; for a genuine crossing sea it is not. The
`fp`/`dir` split cannot fix this because the aggregation publishes no
per-partition directions.

`ef` is log10-encoded
---------------------
This is the trap in this dataset and the reason a naive read is badly wrong.
`ef` has `units = "log10(m2 s+1E-12)"` and `standard_name =
"base_ten_logarithm_of_power_spectral_density_of_surface_elevation"`; on top
of that the wire type is Int16 with `scale_factor = 4e-4`. xarray's
mask_and_scale applies the scale factor and gives the *logarithm*; the linear
spectral density needs the further step

    E(f) = 10**ef - 1e-12

which `decode_ef_spectrum` does. Using `ef` directly yields values around
-3 to +1 that look superficially plausible as a spectrum and are meaningless.

Because this decoding is an inference from the units string rather than from
Ifremer documentation, `spectra_from_iowaga` cross-checks it: it recomputes
Hs = 4*sqrt(integral of E(f) df) from the decoded spectrum and compares
against the dataset's own independently-published `hs`. A wrong decoding
misses by orders of magnitude, so this is a sharp test, and it runs on every
real pull rather than only in tests. See `verify_hs_against_source`.

Facts confirmed against the live service (2026-09-10)
------------------------------------------------------
- The OPeNDAP endpoint, its aggregation name, and that it responds to `.dds`
  and `.das`.
- Dimensions: time = 46752 (nominally 3-hourly, 1991-07-01T00 to
  2019-12-31T21, but see the time-axis corruption above), f = 32,
  latitude = 317 (-78 to 80), longitude = 720 (-180 to 179.5).
- Latitude and longitude ARE strictly monotonic; only time is not.
- `ef` is `Int16 ef[time][f][latitude][longitude]` -- the 1D spectrum is
  present and 4D, not a per-station product.
- `dir` and `spr` carry no `f` dimension, hence the single-lobe limitation
  described above.
- The aggregation has 39 data variables and none of them is a partition
  field, contradicting the catalogue.

Direction convention -- verified, and a trap next door
------------------------------------------------------
`dir` is the direction waves come FROM (clockwise from north), which is
exactly what `forcing/ww3.py::write_ww3_boundary_spectrum` documents for its
`direction` argument, so the lobe is centred on `dir` unrotated and the
output axis is labelled the same way. No conversion is applied and none is
needed.

This is not merely read off the CF standard name. It was measured against
IOWAGA's own point-output spectra (the `POINTS/.../*_spec.nc` files, which
carry a real observed `efth(frequency, direction)`) by computing the
frequency-integrated mean direction from those spectra and comparing it with
the gridded `dir` at the same point and time:

    buoy (30W 52N)    median |delta| = 179.98 deg
    buoy (140W 0N)    median |delta| = 179.91 deg
    buoy (90W 58S)    median |delta| = 179.97 deg

with `spr` and `hs` agreeing to the printed precision at the same points, so
the comparison is sound and the 180 degrees is real. The reason is that those
spectral files declare their direction axis as
`sea_surface_wave_to_direction` -- waves going TO -- while `dir` on the grid
is `sea_surface_wave_from_direction`. Both CF names are therefore honest, and
they corroborate each other.

The trap: if you validate this module's reconstruction against IOWAGA's own
`_spec.nc` files, you MUST rotate one of them by 180 degrees first. Comparing
them raw makes a correct reconstruction look exactly backwards.

Facts NOT confirmed against a real pull (verify and update)
------------------------------------------------------------
- That `E = 10**ef - 1e-12` is the exact intended inverse rather than, say,
  `10**ef` with the 1e-12 being only an encoding floor. The two differ by far
  less than the Hs check's tolerance at any realistic energy level, so the
  Hs check cannot separate them; it only rules out a grossly wrong decoding.
- Nothing further. The direction convention, previously the largest
  unverified assumption here, was checked against real data -- see below.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.raw_data_access.base import *
from CrocoDash.raw_data_access.datasets.utils import convert_lons_to_180_range

THREDDS_DODS_BASE = "https://tds3.ifremer.fr/thredds/dodsC"
THREDDS_CATALOG = (
    "https://tds3.ifremer.fr/thredds/catalogs/IOWAGA-WW3-HINDCAST/"
    "IOWAGA-WW3-HINDCAST.xml"
)

# The global aggregations on the service. The regional ones (ATNE, ATNW, CRB,
# NC, PACE, MED, MEDNORD, ...) follow the same
# IOWAGA-<AREA>_<WIND>-WW3-HINDCAST_FULL_TIME_SERIE naming and are selectable
# through `dataset=`, but only these two have been checked here.
DEFAULT_DATASET = "IOWAGA-GLOBAL_ECMWF-WW3-HINDCAST_FULL_TIME_SERIE"
KNOWN_DATASETS = (
    "IOWAGA-GLOBAL_ECMWF-WW3-HINDCAST_FULL_TIME_SERIE",
    "IOWAGA-GLOBAL_CFSR-WW3-HINDCAST_FULL_TIME_SERIE",
)

# Usable extent of DEFAULT_DATASET, used to reject a bad date range up front
# rather than after a slow request. Only claimed for DEFAULT_DATASET.
#
# The aggregation ADVERTISES 1991-07-01T00 to 2019-12-31T21 (46752 steps), but
# its time axis is broken from 2018 onward and only the prefix below is
# trustworthy. Measured against the live service on 2026-09-10:
#
#   - 46752 steps but only 40912 unique timestamps -- 5840 are duplicates.
#   - 24 backward jumps, all at month boundaries, all in 2018-2019: the axis
#     runs ... 2018-01-31T21 then jumps back to 2018-01-01T00.
#   - The tail past that first jump covers 2018-01-01..2019-12-31 in 11432
#     steps for 5840 unique timestamps, i.e. every 2018-2019 step appears
#     about twice, month-interleaved.
#
# THREDDS is evidently stitching the monthly files in the wrong order there.
# Two copies of a timestamp give no way to tell which slab is right, so this
# module refuses those dates rather than silently picking one. Pandas will not
# even slice a non-monotonic DatetimeIndex by value, so an unguarded
# .sel(time=slice(...)) into that region raises a KeyError that says nothing
# about the real cause.
DEFAULT_DATASET_COVERAGE = ("1991-07-01T00:00:00", "2018-01-31T21:00:00")
DEFAULT_DATASET_ADVERTISED_END = "2019-12-31T21:00:00"

# The additive floor in ef's "log10(m2 s+1E-12)" units string.
EF_LOG_OFFSET = 1e-12

EFTH_UNITS = "m2 s rad-1"
FREQUENCY_UNITS = "s-1"
DIRECTION_COMMENT = (
    "Direction the waves are coming FROM, in degrees clockwise from north "
    "(CF sea_surface_wave_from_direction), matching what "
    "forcing/ww3.py::write_ww3_boundary_spectrum expects."
)

# Number of directional bins synthesized. 24 matches the native directional
# resolution of IOWAGA's own point-output spectra files (efth is 36 frequencies
# x 24 directions there), so the reconstructed spectrum lands on the same
# directional grid the real spectral product uses.
DEFAULT_N_DIRECTIONS = 24

# Hs cross-check tolerances. Loose on purpose: the point is to catch a wrong
# log-decoding (which misses by orders of magnitude), not to police the
# quadrature error of a 32-point trapezoid over a geometric frequency grid,
# which genuinely runs a few percent low because the tail past the last bin is
# not represented.
HS_CHECK_RTOL = 0.15
HS_CHECK_MIN_HS = 0.25


def build_opendap_url(dataset=DEFAULT_DATASET):
    """OPeNDAP endpoint for one IOWAGA aggregation.

    Not validated against KNOWN_DATASETS -- the service carries regional
    aggregations this module has not been tested against, and refusing them
    would be more annoying than useful. A wrong name fails loudly at open
    time with an HTTP error.
    """
    return f"{THREDDS_DODS_BASE}/{dataset}"


def check_coverage(dates, dataset=DEFAULT_DATASET):
    """Raise if `dates` falls outside the aggregation's record.

    Exists because the failure mode otherwise is silent and expensive: an
    out-of-range `.sel(time=slice(...))` on an OPeNDAP dataset returns an
    empty or short selection rather than an error, and the truncation would
    only surface much later as a WW3 boundary file that does not cover the
    run. Only enforced for DEFAULT_DATASET, whose extent was read off the
    live service; other aggregations pass through unchecked.
    """
    if dataset != DEFAULT_DATASET:
        return
    start, stop = (pd.Timestamp(t) for t in DEFAULT_DATASET_COVERAGE)
    first, last = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
    if first < start or last > stop:
        raise ValueError(
            f"{dataset} is usable from {start} to {stop}, but dates {first} "
            f"to {last} were requested. The aggregation advertises data to "
            f"{pd.Timestamp(DEFAULT_DATASET_ADVERTISED_END)}, but its time "
            "axis is broken from 2018 on -- each month appears about twice "
            "and out of order, so a slice of it cannot be trusted. The "
            "OPeNDAP service also does not carry the newer "
            "GLOBMULTI_ERA5_GLOBCUR_01 hindcast (1993-2024, ERA5 forcing) at "
            "all. For dates outside the usable range use the "
            "data-dataref.ifremer.fr file tree instead. See this module's "
            "docstring."
        )


def decode_ef_spectrum(ef, log_offset=EF_LOG_OFFSET):
    """Undo IOWAGA's log10 encoding of the 1D frequency spectrum.

    `ef` arrives from xarray already unpacked by scale_factor, but still as
    a base-10 logarithm (units "log10(m2 s+1E-12)"), so the linear spectral
    density in m2 s is 10**ef - log_offset. See the module docstring; this is
    the single easiest thing to get wrong about this dataset.

    Negatives from the subtraction at near-zero energy are clipped to 0 --
    they are encoding noise around the floor, and a negative spectral density
    would poison the Hs integral.
    """
    linear = np.power(10.0, ef) - log_offset
    return linear.clip(min=0.0)


def cosine_2s_spread(direction_deg, mean_direction_deg, spread_deg):
    """Normalized cosine-2s directional distribution D(theta), in rad^-1.

    D(theta) = N * cos^(2s)((theta - theta_m) / 2), with s recovered from the
    circular directional spread by the standard relation for this family,
    sigma^2 = 2 / (s + 1), i.e. s = 2 / sigma^2 - 1 with sigma in radians.

    Computed in log space -- 2s * log(cos(dtheta/2)) with the max subtracted
    before exponentiating -- rather than as a direct power. A narrow swell
    with a spread of a degree or two gives s in the thousands, and
    cos(x)**(2s) evaluated directly underflows to zero in every bin including
    the peak, silently producing an all-zero spectrum. The log form is exact
    for arbitrarily large s.

    Normalization is done numerically against the actual direction grid, not
    by the analytic Gamma-function constant, so that sum(D) * dtheta == 1 on
    the discrete bins that get written. That is what makes the reconstructed
    Hs match the source Hs exactly rather than to within a quadrature error.

    Parameters
    ----------
    direction_deg : 1D array, the direction bin centres in degrees.
    mean_direction_deg, spread_deg : arrays of matching shape, broadcast
        against the direction axis, in degrees. NaN (typically land) or a
        non-positive spread yields a uniform lobe, so those points carry
        whatever energy E(f) has rather than NaN-poisoning the file.

    Returns
    -------
    Array of shape mean_direction_deg.shape + (n_directions,), in rad^-1.
    """
    direction = np.deg2rad(np.asarray(direction_deg, dtype=np.float64))
    n_dir = direction.size
    dtheta = 2.0 * np.pi / n_dir

    mean_direction = np.deg2rad(np.asarray(mean_direction_deg, dtype=np.float64))
    spread = np.deg2rad(np.asarray(spread_deg, dtype=np.float64))

    # s = 2/sigma^2 - 1, floored at 0 (sigma = sqrt(2) rad is the isotropic
    # limit of this family; a larger spread cannot be represented and becomes
    # uniform rather than a negative exponent).
    with np.errstate(divide="ignore", invalid="ignore"):
        s = 2.0 / np.square(spread) - 1.0
    degenerate = ~np.isfinite(s) | (s <= 0.0) | ~np.isfinite(mean_direction)
    s = np.where(degenerate, 0.0, s)

    delta = (
        direction.reshape((1,) * mean_direction.ndim + (n_dir,))
        - mean_direction[..., None]
    )
    half = 0.5 * np.where(np.isfinite(delta), delta, 0.0)

    # cos(half) < 0 on the far half of the circle -> zero energy there.
    cos_half = np.cos(half)
    positive = cos_half > 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        log_lobe = 2.0 * s[..., None] * np.log(np.where(positive, cos_half, 1.0))
    log_lobe = np.where(positive, log_lobe, -np.inf)

    log_lobe -= np.nanmax(
        np.where(np.isfinite(log_lobe), log_lobe, -np.inf), axis=-1, keepdims=True
    )
    lobe = np.exp(log_lobe)
    lobe = np.where(np.isfinite(lobe), lobe, 0.0)

    lobe = np.where(degenerate[..., None], 1.0, lobe)

    total = lobe.sum(axis=-1, keepdims=True) * dtheta
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized = np.where(total > 0.0, lobe / total, 1.0 / (n_dir * dtheta))
    return normalized


def significant_height_from_ef(ef_linear, frequency):
    """Hs = 4 * sqrt(integral E(f) df), for the decoded 1D spectrum.

    Trapezoidal over the native geometric frequency grid. This runs a few
    percent low against the model's own Hs because the energy above the last
    bin is not represented; HS_CHECK_RTOL is set with that in mind.
    """
    frequency = np.asarray(frequency, dtype=np.float64)
    axis = (
        ef_linear.get_axis_num("frequency")
        if hasattr(ef_linear, "get_axis_num")
        else -1
    )
    values = np.asarray(ef_linear, dtype=np.float64)
    m0 = np.trapezoid(values, x=frequency, axis=axis)
    return 4.0 * np.sqrt(np.clip(m0, 0.0, None))


def verify_hs_against_source(
    ef_linear, frequency, source_hs, rtol=HS_CHECK_RTOL, min_hs=HS_CHECK_MIN_HS
):
    """Cross-check the log10 decoding against the dataset's published `hs`.

    Returns a dict of diagnostics (written into the output file's attrs) and
    raises if the two disagree beyond `rtol`. A wrong decoding -- forgetting
    the 10** entirely, say -- is off by orders of magnitude, so this is a
    sharp test of the one inference in this module that Ifremer does not
    document.

    Only points with source Hs above `min_hs` are scored: at near-zero energy
    the relative error is dominated by the encoding floor and would trip the
    check for no physical reason.
    """
    reconstructed = significant_height_from_ef(ef_linear, frequency)
    published = np.asarray(source_hs, dtype=np.float64)

    scored = np.isfinite(reconstructed) & np.isfinite(published) & (published > min_hs)
    n_scored = int(scored.sum())
    if n_scored == 0:
        return {
            "hs_check": "skipped -- no points above the minimum significant height",
            "hs_check_n_points": 0,
        }

    relative = (reconstructed[scored] - published[scored]) / published[scored]
    median_bias = float(np.median(relative))
    diagnostics = {
        "hs_check": "passed",
        "hs_check_n_points": n_scored,
        "hs_check_median_relative_bias": median_bias,
        "hs_check_p95_absolute_relative_error": float(
            np.percentile(np.abs(relative), 95)
        ),
        "hs_check_rtol": rtol,
    }
    if abs(median_bias) > rtol:
        raise ValueError(
            "IOWAGA ef decoding failed its self-check: significant height "
            f"recomputed from the decoded 1D spectrum is off by a median "
            f"{median_bias:+.1%} against the dataset's own published `hs` "
            f"over {n_scored} points (tolerance {rtol:.0%}). The assumed "
            "encoding is E(f) = 10**ef - 1e-12; if Ifremer has changed it, "
            "fix decode_ef_spectrum in "
            "raw_data_access/datasets/iowaga.py."
        )
    return diagnostics


def _select_window(
    ds,
    dates,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    buffer_deg=1.0,
    normalize_longitudes=True,
):
    """Subset the aggregation to the requested time/space window.

    Returns a LIST of still-lazy pieces -- one normally, two when the window
    straddles the antimeridian. `_load_window` turns that into a single
    dataset. Keeping them separate is what lets each side be fetched as its
    own contiguous OPeNDAP request; see `_load_window`.

    This is where the OPeNDAP win is realized: nothing has travelled over the
    wire yet, and when it does only these indices do.

    Why not `mom6_forge.utils.longitude_slicer`, which glorys.py uses for the
    same job: it handles the seam by `roll`ing the dataset and then indexing
    the rolled copy. That is right for a dataset already in memory, but a roll
    of a remote 46752 x 32 x 317 x 720 aggregation would pull the entire globe
    across the network -- exactly what OPeNDAP subsetting exists to avoid.
    The shared `convert_lons_to_180_range` IS used, so the two products agree
    on longitude convention even though they cannot share the slicer.

    The +/- buffer_deg padding matches era5.py's convention and exists for
    the same reason -- a boundary bounding box from
    mom6_forge.Grid.get_bounding_boxes is a near-zero-width strip, which
    would otherwise select zero or one grid points.

    Latitude is sliced with an explicit ascending/descending check rather
    than assuming a direction: xarray's .sel with a slice silently returns
    nothing if the slice runs opposite to the coordinate's order.
    """
    if normalize_longitudes:
        lon_min, lon_max = convert_lons_to_180_range(lon_min, lon_max)

    ds = ds.isel(time=_time_index_slice(ds["time"].values, dates))

    lat_slice = slice(lat_min - buffer_deg, lat_max + buffer_deg)
    if ds["latitude"].values[0] > ds["latitude"].values[-1]:
        lat_slice = slice(lat_slice.stop, lat_slice.start)
    ds = ds.sel(latitude=lat_slice)

    west = lon_min - buffer_deg
    east = lon_max + buffer_deg
    if west < east:
        pieces = [ds.sel(longitude=slice(west, east))]
    else:
        # Crosses the antimeridian: [west, 180] plus [-180, east]. Two
        # contiguous slices rather than one that would select nothing, since
        # the longitude axis is a monotonic -180..179.5.
        pieces = [
            ds.sel(longitude=slice(west, 180.0)),
            ds.sel(longitude=slice(-180.0, east)),
        ]

    n_lon = sum(piece.sizes.get("longitude", 0) for piece in pieces)
    if ds.sizes.get("latitude", 0) == 0 or n_lon == 0:
        raise ValueError(
            f"No IOWAGA grid points in lat [{lat_min}, {lat_max}] lon "
            f"[{lon_min}, {lon_max}] (buffer {buffer_deg} deg). The grid is "
            "0.5 degree, spanning -78 to 80 north."
        )
    return [piece for piece in pieces if piece.sizes.get("longitude", 0) > 0]


def _time_index_slice(time_values, dates):
    """Contiguous integer slice covering `dates`, from a local time array.

    Used instead of `.sel(time=slice(...))` for two reasons, both specific to
    this aggregation:

    1. Its time axis is non-monotonic past 2018 (see
       DEFAULT_DATASET_COVERAGE). Pandas refuses to value-slice a
       non-monotonic DatetimeIndex and raises a KeyError whose text names
       nothing relevant; `check_coverage` should have caught the date range
       first, and this asserts that invariant with a message that explains
       itself.
    2. An integer slice is a single contiguous OPeNDAP request, whereas
       value-based selection on a remote index can degrade into fancy
       indexing.

    The coordinate array is already local -- xarray reads coordinates eagerly
    when it opens the dataset -- so this costs no extra network traffic.
    """
    times = pd.DatetimeIndex(np.asarray(time_values))
    start, stop = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])

    first = int(np.searchsorted(times.values, np.datetime64(start), side="left"))
    last = int(np.searchsorted(times.values, np.datetime64(stop), side="right"))
    if last <= first:
        raise ValueError(f"No IOWAGA time steps between {dates[0]} and {dates[-1]}.")

    span = times[first:last]
    if not span.is_monotonic_increasing:
        raise ValueError(
            f"The IOWAGA aggregation's time axis is not monotonic between "
            f"{dates[0]} and {dates[-1]}, so a slice of it cannot be trusted. "
            "This affects 2018 onward, where the service repeats each month "
            "roughly twice and out of order. Use the "
            "data-dataref.ifremer.fr file tree for those dates."
        )
    return slice(first, last)


def _load_window(pieces):
    """Load the lazy pieces from `_select_window` and join them.

    Each piece is loaded on its own BEFORE concatenation, which matters when
    a window straddles the antimeridian. Concatenating two lazy
    OPeNDAP-backed selections and loading the result makes xarray fetch
    through the combined (non-contiguous) index and is roughly an order of
    magnitude slower than issuing one contiguous request per side; the join
    is then a cheap in-memory operation.
    """
    loaded = [piece.load() for piece in pieces]
    if len(loaded) == 1:
        return loaded[0]
    return xr.concat(loaded, dim="longitude")


def spectra_from_iowaga(
    ds,
    n_directions=DEFAULT_N_DIRECTIONS,
    direction=None,
    check_hs=True,
    dtype=np.float32,
):
    """Build E(f, theta) from a loaded IOWAGA window.

    Pure -- no I/O -- so it is unit-testable from a fabricated dataset with
    no network, mirroring how the ERA5 products separate their assembly step.

    Returns a Dataset with exactly ONE data variable, `efth`, on dims
    (time, latitude, longitude, frequency, direction). The single-variable
    part is a hard requirement, not style: forcing/ww3.py::
    _extract_all_stations does `(var_name,) = ds.data_vars`, so a second
    variable breaks the WW3 pipeline with an unpacking error. Diagnostics go
    in attrs.
    """
    for required in ("ef", "dir", "spr"):
        if required not in ds:
            raise KeyError(
                f"IOWAGA window is missing {required!r}, which the 2D "
                f"reconstruction needs. Variables present: "
                f"{sorted(ds.data_vars)}."
            )

    frequency = np.asarray(ds["f"].values, dtype=np.float64)
    if direction is None:
        direction = np.arange(n_directions, dtype=np.float64) * (360.0 / n_directions)
    direction = np.asarray(direction, dtype=np.float64)

    ef = ds["ef"].transpose("time", "latitude", "longitude", "f")
    ef_linear = decode_ef_spectrum(ef)

    diagnostics = {}
    if check_hs and "hs" in ds:
        diagnostics = verify_hs_against_source(
            ef_linear.rename({"f": "frequency"}),
            frequency,
            ds["hs"].transpose("time", "latitude", "longitude").values,
        )
    elif check_hs:
        diagnostics = {"hs_check": "skipped -- no `hs` in the fetched window"}

    lobe = cosine_2s_spread(
        direction,
        ds["dir"].transpose("time", "latitude", "longitude").values,
        ds["spr"].transpose("time", "latitude", "longitude").values,
    )

    # (t, y, x, f) x (t, y, x, theta) -> (t, y, x, f, theta). Land is NaN in
    # ef; zero it so those stations are simply zero-energy, which
    # forcing/ww3.py tolerates, rather than NaN, which ww3_bounc does not.
    efth = (
        np.nan_to_num(np.asarray(ef_linear.values, dtype=np.float64))[..., :, None]
        * lobe[..., None, :]
    )

    provenance = {
        "reconstruction": (
            "observed IOWAGA 1D frequency spectrum x cosine-2s directional "
            "lobe from the frequency-integrated mean direction and spread"
        ),
        "source": "IOWAGA WAVEWATCH-III hindcast via Ifremer THREDDS OPeNDAP",
        "source_variables": "ef,dir,spr",
        "ef_decoding": "E(f) = 10**ef - 1e-12",
        "directional_limitation": (
            "dir and spr are frequency-integrated, so every frequency band "
            "shares one mean direction and spread; crossing seas collapse to "
            "a single smeared lobe"
        ),
        "n_directions": int(direction.size),
        **{k: v for k, v in diagnostics.items()},
        **{
            k: v
            for k, v in ds.attrs.items()
            if k in ("title", "source", "WAVEWATCH_III_version_number", "area")
        },
    }

    return xr.Dataset(
        {
            "efth": (
                ("time", "latitude", "longitude", "frequency", "direction"),
                efth.astype(dtype),
                {
                    "units": EFTH_UNITS,
                    "long_name": (
                        "2D wave energy density spectrum (observed 1D "
                        "spectrum with a synthesized directional lobe)"
                    ),
                    **provenance,
                },
            )
        },
        coords={
            "time": ds["time"].values,
            "latitude": ds["latitude"].values,
            "longitude": ds["longitude"].values,
            "frequency": ("frequency", frequency, {"units": FREQUENCY_UNITS}),
            "direction": (
                "direction",
                direction,
                {"units": "degree", "comment": DIRECTION_COMMENT},
            ),
        },
        attrs=provenance,
    )


class IOWAGA(WW3ForcingProduct):
    product_name = "iowaga"
    description = (
        "IOWAGA WAVEWATCH-III global wave hindcast (Ifremer/LOPS), read "
        "through the THREDDS OPeNDAP service so the time/space window is "
        "subset server-side instead of downloading ~2.8 GB monthly global "
        "files. Supplies WW3 boundary spectra E(f, theta) built from the "
        "hindcast's observed 1D frequency spectrum combined with a "
        "cosine-2s directional lobe. NOTE: OPeNDAP carries the ECMWF-forced "
        "hindcast (1991-2019), not the newer ERA5-forced "
        "GLOBMULTI_ERA5_GLOBCUR_01 (1993-2024), which is file-server only."
    )
    link = "https://tds3.ifremer.fr/thredds/catalogs/IOWAGA-WW3-HINDCAST/IOWAGA-WW3-HINDCAST.xml"
    time_var_name = "time"
    time_units = "hours"
    calendar = GREGORIAN

    @classmethod
    def validate_method(cls, method_name, **kwargs):
        """Not auto-validatable: it needs the live Ifremer THREDDS service.

        docs/source/raw_data_access/check_raw_data.py calls
        ProductRegistry.validate_function on every registered product from a
        nightly runner. A toy call here would make a real OPeNDAP request to
        a third-party server, so the nightly job's result would track
        Ifremer's uptime rather than this repo's correctness. Return False,
        which is what BaseProduct.validate_method returns on error anyway.
        """
        cls.logger.info(
            "%s cannot be auto-validated: it needs the live "
            "tds3.ifremer.fr THREDDS service.",
            cls.product_name,
        )
        return False

    @accessmethod(
        description=(
            "Subsets the IOWAGA hindcast over OPeNDAP to the requested "
            "window and writes a 2D wave spectrum E(f, theta) in the same "
            "(time, latitude, longitude, frequency, direction) shape as the "
            "ERA5 wave-spectra products, so it is a drop-in replacement for "
            "them. No API key and no local staging of global files."
        ),
        type="python",
        how_to_use=(
            "Set ww3_obc_product_name='iowaga' and "
            "ww3_obc_function_name='get_iowaga_2d_spectra' on "
            "WW3Configurator. Needs outbound HTTPS to tds3.ifremer.fr and no "
            "credentials. Knobs (dataset, n_directions, buffer_deg, "
            "check_hs) are passed through WW3Configurator's "
            "ww3_obc_extra_args. Dates must fall in 1991-07-01..2019-12-31; "
            "for later dates use the data-dataref file server instead."
        ),
    )
    def get_iowaga_2d_spectra(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="iowaga_spectra.nc",
        variables=None,
        dataset=DEFAULT_DATASET,
        n_directions=DEFAULT_N_DIRECTIONS,
        buffer_deg=1.0,
        check_hs=True,
        normalize_longitudes=True,
    ):
        # `variables` exists only to satisfy ForcingProduct.required_args.
        # It cannot select what gets fetched: the reconstruction needs
        # exactly ef/dir/spr (plus hs for the self-check), and forcing/ww3.py
        # calls the shared OBC engine with a hardcoded variables=[], so
        # honouring it would mean requesting nothing on every real call.
        if variables:
            raise ValueError(
                "iowaga does not take a `variables` list -- the 2D "
                "reconstruction always needs ef, dir and spr (and hs for its "
                f"self-check). Got variables={variables!r}."
            )

        check_coverage(dates, dataset)

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename

        wanted = ["ef", "dir", "spr", "hs"]
        with xr.open_dataset(build_opendap_url(dataset)) as remote:
            available = [v for v in wanted if v in remote.data_vars]
            missing = set(wanted[:3]) - set(available)
            if missing:
                raise KeyError(
                    f"{dataset} does not publish {sorted(missing)}, which the "
                    "2D reconstruction needs. Note the THREDDS catalogue's "
                    "variable list is the union over the product family and "
                    "over-advertises; this checks the live dataset. "
                    f"Available: {sorted(remote.data_vars)}."
                )
            pieces = _select_window(
                remote[available],
                dates=dates,
                lat_min=lat_min,
                lat_max=lat_max,
                lon_min=lon_min,
                lon_max=lon_max,
                buffer_deg=buffer_deg,
                normalize_longitudes=normalize_longitudes,
            )
            # The one network transfer: only the selected window travels,
            # as one contiguous request per piece.
            window = _load_window(pieces)

        spectra = spectra_from_iowaga(
            window, n_directions=n_directions, check_hs=check_hs
        )
        spectra.to_netcdf(
            output_path, encoding={"efth": {"zlib": True, "complevel": 1}}
        )
        return output_path
