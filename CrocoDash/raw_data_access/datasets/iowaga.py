"""
Data Access Module -> IOWAGA GLOBMULTI_ERA5_GLOBCUR_01 2D wave spectra

Builds WW3 boundary spectra E(f, theta) from the spectral partitioning of
Ifremer's GLOBMULTI_ERA5_GLOBCUR_01 wave hindcast, fetched from the
data-dataref file server.

Which hindcast this is, and why not OPeNDAP
-------------------------------------------
This is the current IOWAGA product: WAVEWATCH-III v7.08, ERA5 winds,
CMEMS-GLOBCURRENT currents, CERSAT ice and ALTIBERG icebergs, Alday et al.
(2021) physics, **1993-01 to 2026-03** and still growing. It is the dataset
with the Sextant DOI (10.12770/857a3337-f59a-481a-bf98-5561e8b61e7b).

An earlier version of this module read Ifremer's THREDDS OPeNDAP service
instead, for server-side subsetting. That was abandoned, and it is worth
recording why so nobody re-treads it. Verified against the live services on
2026-09-10:

  * GLOBMULTI_ERA5_GLOBCUR_01 is **not on OPeNDAP at all**. Searching the
    whole tds3 IOWAGA catalogue for globmulti/era5/globcur returns nothing;
    the dataset's THREDDS directory holds only a staging folder named
    `toremove/`. Only tds0/tds1/tds3 exist and only tds3 carries IOWAGA.
  * What OPeNDAP does serve is `IOWAGA-GLOBAL_ECMWF`, a different and older
    run (WW3 v6.07, ECMWF operational winds, BETAMAX 1.5).
  * That aggregation is also corrupt past 2018-01-31: 46752 steps for 40912
    unique timestamps, 24 backward jumps at month boundaries, each 2018-2019
    month appearing about twice and out of order. Confirmed on the RAW
    undecoded time values, so it is the server, not a decoding artifact.

The point-output spectra (`POINTS/<year>/SPEC_*/`) were also considered,
since they carry true observed 2D spectra rather than a reconstruction. They
are unusable as a general boundary source: the virtual buoys are clustered
near coasts. Measured over the 10808 points published for 1993, a coastal box
holds 0.4-0.8 points per square degree, but an open-ocean 10x10 degree box in
the North Atlantic (40W-30W, 45N-55N) holds **two**. A regional domain's
offshore boundary would have almost no stations.

So: gridded partitions from the file server, reconstructed into spectra.

How the 2D spectrum is built
----------------------------
The monthly files carry a six-way spectral partitioning -- partition 0 is the
wind sea, 1-5 are swell systems ordered by energy -- with five fields each
that are exactly what a parametric reconstruction needs:

    phs0-5   significant height of the partition          m
    ptp0-5   PEAK period of the partition                 s
    pdir0-5  mean direction, coming-from, cw from north   degree
    pspr0-5  directional spread of the partition          degree
    pws0-5   wind-sea fraction within the partition       1

plus three whole-spectrum fields, `hs`, `t0m1` and `t02`.

Each partition becomes a normalised frequency shape peaked at 1/ptp -- blended
between a wind-sea family and a swell family by `pws` -- scaled so its
significant height is exactly phs, multiplied by a cosine-2s directional lobe
centred on pdir with spread pspr. The partitions are then summed.

The shape itself is NOT assumed. The reconstruction is Hell's `ww3recon`
(vendored at `raw_data_access/ww3recon/`, see its `__init__` for provenance
and for what was deliberately left out), which fits two free shape parameters
-- wind-sea peakedness and swell width -- per point by matching the archive's
own `t0m1`, then calibrates the high-frequency exponent against `t02` in a
second stage. `t0m1` is weighted toward the low-frequency flank where
peakedness lives, which is what makes it the informative constraint; `t02` is
tail-dominated, which is what makes it the right one for the exponent.

Only one constraint is available for two unknowns, so weak priors break the
degeneracy. Points containing only one family are exactly determined and are
flagged `underconstrained_ws`/`underconstrained_sw` in the summary attrs.

Two things make this materially better than the equivalent reconstruction
from ERA5 bulk statistics (`era5_wave_stats.py`):

  * `ptp` is a true peak period -- its standard_name is
    `sea_surface_wave_period_at_variance_spectral_density_maximum` -- which
    is exactly the parameter the frequency shape's peak wants. The ERA5 route
    has only Tm(-1,0) and must assume a moment order to convert.
  * Every partition carries its **own** directional spread. ERA5 publishes no
    per-swell-partition width and has to reuse the total-swell width across
    all of them, biasing individual partitions toward over-spread.

And six partitions resolve a crossing sea that the ERA5 route's two-to-four
would merge.

The partitions are energy-complete, which is what makes this trustworthy:
measured on 1993-01, the median of sqrt(sum_i phs_i^2) / hs over points with
hs > 0.5 m is **1.0000**. Nothing is lost to an unrepresented residual, so
unlike the ERA5 route there is no need to synthesize one. Absent partitions
are NaN (not zero) and are simply skipped.

What is still assumed: the frequency shape within each partition comes from a
parametric family rather than being observed. Significant height, peak period
and mean direction are reproduced by construction, and peakedness and tail
slope are now fitted rather than assumed, but the family is still a choice.
The defaults (Elfouhaily wind sea, Ochi-Hubble swell) were selected by Hell on
four IOWAGA sites for January 1993 -- a four-site, one-month result, not a
global or seasonal sweep. Swap them with `windsea_family`/`swell_family` and
rank them on your own domain before relying on the shape.

`spectra_from_partitions` cross-checks the result against the file's own `hs`
on every real call -- see `verify_hs_against_source`. Note that the check
integrates with WW3's geometric bin width, the same rule the reconstruction
normalises against; integrating with a trapezoid instead would report the gap
between two quadrature rules as a bias in the reconstruction.

Validation against IOWAGA's own 2D spectra
------------------------------------------
The archive publishes true WW3 2D spectra at ~10,800 virtual buoys, which is
the only ground truth there is for this. This module was scored against them
for all 248 timesteps of January 1993, at the nearest gridded cell to three
buoys spanning three regimes (`dev/iowaga/validate_against_truth.py`):

| site                    | spectral corr | p10  | Hs bias |
|-------------------------|---------------|------|---------|
| mid N Atlantic 30W 52N  | 0.873         | 0.80 | +0.01%  |
| equatorial Pacific 140W | 0.904         | 0.85 | +0.03%  |
| Southern Ocean 90W 58S  | 0.867         | 0.80 | +0.00%  |

That is three sites and one month, so it is a sanity floor rather than a skill
estimate: no seasonal coverage, no shallow water, no ice, and the buoy is
compared against the grid cell containing it, so some of the residual is
sampling rather than reconstruction. Re-run the harness on your own domain
before relying on the shape.

The same run is what pins the direction convention: comparing against the
truth spectra with the direction axis mirrored instead of rotated scores
0.15-0.17 at all three sites. A convention error is not subtle here, but it is
also not visibly wrong in any single plot, which is why it is checked
numerically rather than by eye.

Cost, and why the whole file comes down
----------------------------------------
The monthly global files are ~2.8 GB and the 33 variables used here are ~38%
of the data, so a lazy range-read would save ~3.5x. That is not done, for a
concrete reason: the files are NETCDF4 chunked `[1, 323, 720]`, i.e. one
chunk is a whole global timestep, so spatial subsetting saves nothing within
a timestep and only the variable/time selection would help. Reading remotely
that way needs `fsspec[http]`, which pulls in `aiohttp` -- not currently in
CrocoDash's environment. Against that, the server honours byte ranges and
throttles per connection, so a parallel-chunk download of a whole month takes
about 15-25 seconds (measured: 2.7 GB in 17 s at 16 chunks). Downloading the
month, subsetting it locally and deleting it is simpler, adds no dependency,
and is not the bottleneck. Set `keep_raw=True` to retain the monthly files.

Peak transient disk is one monthly file (~2.8 GB); months are processed and
deleted one at a time, so a multi-year request does not accumulate.

Direction convention -- verified
--------------------------------
`pdir` is `sea_surface_wave_from_direction_partition_N`: the direction waves
come FROM, clockwise from north. That is exactly what
`forcing/ww3.py::write_ww3_boundary_spectrum` documents for its `direction`
argument, so lobes are centred on `pdir` unrotated and the output axis is
labelled the same way.

This was checked against real data rather than taken from the CF name. The
frequency-integrated mean direction computed from IOWAGA's own point-output
spectra sits 180 degrees from the gridded `dir` at the same points and times
(median |delta| = 179.98, 179.91, 179.97 degrees at three buoys, with `spr`
and `hs` agreeing to printed precision, so the comparison is sound). The
reason is that those spectral files declare a `sea_surface_wave_to_direction`
axis while the gridded directions are from-direction. Both CF names are
honest and they corroborate each other.

The trap: if you validate this module against IOWAGA's own `_spec.nc` files,
rotate one of them by 180 degrees first. Compared raw, a correct
reconstruction looks exactly backwards.
"""

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.raw_data_access.base import *
from CrocoDash.raw_data_access.datasets.utils import convert_lons_to_180_range
from CrocoDash.raw_data_access.ww3recon import (
    PartitionSet,
    ReconstructionConfig,
    Reconstructor,
    SpectralGrid,
)

FILE_SERVER_BASE = "https://data-dataref.ifremer.fr/ww3/GLOBMULTI_ERA5_GLOBCUR_01"
GRID_NAME = "GLOB-30M"

# Earliest month published. The end is deliberately NOT hardcoded -- the
# hindcast is extended over time (2026-03 was the last month available on
# 2026-09-10), so `available_months` reads the server's own directory listing
# instead of going stale.
DATASET_START = "1993-01-01T00:00:00"

N_PARTITIONS = 6
# `pws` (the wind-sea fraction within each partition) is read as well as the
# four shape parameters: it decides how each partition is blended between the
# wind-sea and swell frequency families.
PARTITION_FIELDS = ("phs", "ptp", "pdir", "pspr", "pws")
# `hs` is fetched too, purely so verify_hs_against_source has an independent
# reference; it takes no part in the reconstruction.
REFERENCE_FIELD = "hs"
# Whole-spectrum mean periods. `t0m1` is REQUIRED -- it is the single
# constraint the per-point peakedness fit is solved against, and without it
# there is nothing to fit. `t02` is optional and drives the second-stage
# tail-exponent fit; without it the tail stays at the family default.
T0M1_FIELD = "t0m1"
T02_FIELD = "t02"

# IOWAGA's native spectral discretization, read off its own point-output
# spectra files: 36 frequencies, f0 = 0.0339 Hz, geometric ratio 1.1, and 24
# directions. Reconstructing onto the same grid the real spectral product
# uses means ww3_bounc's SPCONV remapping has the least work to do.
IOWAGA_F0 = 0.0339
IOWAGA_FREQUENCY_RATIO = 1.1
IOWAGA_N_FREQUENCIES = 36
DEFAULT_N_DIRECTIONS = 24

# Frequency-shape families, passed through to ww3recon. These defaults are
# Hell's, selected on four IOWAGA sites for January 1993: Elfouhaily wind sea
# plus Ochi-Hubble swell scored 0.901 mean spectral correlation against the
# archive's own point-output spectra, where every Gaussian-swell combination
# scored ~0.69. The swell family is the choice that matters -- the four
# wind-sea families land within 0.004 of each other. This is a four-site,
# one-month result, not a global sweep.
DEFAULT_WINDSEA_FAMILY = "elfouhaily"
DEFAULT_SWELL_FAMILY = "ochi_hubble"

# Points reconstructed per block. The reconstruction is a dense
# (n_points, n_frequency, n_direction) float64 array, so this is what bounds
# peak memory: 20000 points on the native 36x24 grid is ~140 MB, independent
# of how large a domain or how long a date range was asked for.
DEFAULT_POINT_BLOCK = 20000

EFTH_UNITS = "m2 s rad-1"
FREQUENCY_UNITS = "s-1"
DIRECTION_COMMENT = (
    "Direction the waves are coming FROM, in degrees clockwise from north "
    "(CF sea_surface_wave_from_direction), matching what "
    "forcing/ww3.py::write_ww3_boundary_spectrum expects."
)

# Parallel byte-range chunks per monthly file. The server throttles per
# connection but honours ranges, so this is the difference between ~20 s and
# several minutes for one month.
DEFAULT_N_CHUNKS = 16
DOWNLOAD_RETRIES = 4

# Hs cross-check tolerance. Loose on purpose: it exists to catch a structural
# mistake (wrong field, wrong partition indexing, lost energy), not to police
# the difference between a JONSWAP shape and the real one.
HS_CHECK_RTOL = 0.10
HS_CHECK_MIN_HS = 0.25


def iowaga_frequencies(
    n=IOWAGA_N_FREQUENCIES, f0=IOWAGA_F0, ratio=IOWAGA_FREQUENCY_RATIO
):
    """IOWAGA's native geometric frequency grid, in Hz."""
    return f0 * ratio ** np.arange(n, dtype=np.float64)


def build_month_url(year, month, grid=GRID_NAME, base=FILE_SERVER_BASE):
    """URL of one monthly field file."""
    return f"{base}/{grid}/{year:04d}/FIELD_NC/LOPS_WW3-{grid}_{year:04d}{month:02d}.nc"


def months_in_range(dates):
    """[(year, month), ...] covering `dates`, inclusive at both ends."""
    start, stop = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
    if stop < start:
        raise ValueError(f"dates run backwards: {dates[0]} to {dates[-1]}.")
    periods = pd.period_range(start.to_period("M"), stop.to_period("M"), freq="M")
    return [(p.year, p.month) for p in periods]


def available_months(year, grid=GRID_NAME, base=FILE_SERVER_BASE):
    """Months published for `year`, read from the server's directory listing.

    Used instead of a hardcoded end date because the hindcast is extended
    over time. Returns an empty list for a year with no directory, which the
    caller reports as an out-of-range request.
    """
    url = f"{base}/{grid}/{year:04d}/FIELD_NC/"
    try:
        with urlopen(Request(url), timeout=120) as response:
            listing = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        if error.code == 404:
            return []
        raise
    prefix = f"LOPS_WW3-{grid}_{year:04d}"
    found = set()
    for token in listing.split('href="'):
        name = token.split('"')[0]
        if name.startswith(prefix) and name.endswith(".nc") and "_p2l" not in name:
            tail = name[len(prefix) :].removesuffix(".nc")
            if tail.isdigit() and len(tail) == 2:
                found.add(int(tail))
    return sorted(found)


def check_coverage(dates, grid=GRID_NAME, base=FILE_SERVER_BASE):
    """Raise if any month in `dates` is not published.

    Checks the server rather than a hardcoded end, so this does not go stale
    as Ifremer extends the hindcast. One small directory listing per distinct
    year -- negligible next to a 2.8 GB monthly file.
    """
    start = pd.Timestamp(DATASET_START)
    first = pd.Timestamp(dates[0])
    if first < start:
        raise ValueError(
            f"GLOBMULTI_ERA5_GLOBCUR_01 begins {start:%Y-%m}, but "
            f"{first:%Y-%m-%d} was requested."
        )
    by_year = {}
    for year, month in months_in_range(dates):
        by_year.setdefault(year, set()).add(month)
    for year in sorted(by_year):
        published = set(available_months(year, grid=grid, base=base))
        missing = sorted(by_year[year] - published)
        if missing:
            extra = (
                f" (and {len(missing) - 1} more month(s) in {year})"
                if len(missing) > 1
                else ""
            )
            have = (
                ", ".join(f"{m:02d}" for m in sorted(published))
                if published
                else "nothing"
            )
            raise ValueError(
                f"GLOBMULTI_ERA5_GLOBCUR_01 has no {grid} data for "
                f"{year}-{missing[0]:02d}{extra}. Published for that year: "
                f"{have}. See {base}/{grid}/."
            )


def _content_length(url):
    with urlopen(Request(url, method="HEAD"), timeout=120) as response:
        length = response.headers.get("Content-Length")
    if length is None:
        raise ValueError(f"{url} did not report a Content-Length.")
    return int(length)


def _fetch_range(url, start, stop, destination):
    """One byte range to one part file, with retries."""
    last_error = None
    for _ in range(DOWNLOAD_RETRIES):
        try:
            request = Request(url, headers={"Range": f"bytes={start}-{stop}"})
            with urlopen(request, timeout=1800) as response, open(
                destination, "wb"
            ) as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            return
        except Exception as error:  # network flakiness, not a logic error
            last_error = error
    raise RuntimeError(f"failed to fetch bytes {start}-{stop} of {url}: {last_error}")


def download_month(url, destination, n_chunks=DEFAULT_N_CHUNKS):
    """Download one monthly file as `n_chunks` parallel byte ranges.

    The server throttles per connection but sets `accept-ranges: bytes`, so
    splitting the file across parallel range requests is the difference
    between ~20 seconds and several minutes for one 2.8 GB month.

    Skips the download when a correctly sized file is already in place, which
    makes a re-run after a partial failure cheap and lets a caller stage
    files by hand.
    """
    destination = Path(destination)
    size = _content_length(url)
    if destination.exists() and destination.stat().st_size == size:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    per_chunk = -(-size // n_chunks)
    spans = []
    for index in range(n_chunks):
        start = index * per_chunk
        stop = min(start + per_chunk - 1, size - 1)
        if start <= stop:
            spans.append((start, stop))

    parts = [destination.with_suffix(f".part{i:03d}") for i in range(len(spans))]
    try:
        with ThreadPoolExecutor(max_workers=len(spans)) as pool:
            list(
                pool.map(
                    lambda pair: _fetch_range(url, pair[0][0], pair[0][1], pair[1]),
                    zip(spans, parts),
                )
            )
        with open(destination, "wb") as handle:
            for part in parts:
                with open(part, "rb") as chunk:
                    shutil.copyfileobj(chunk, handle, length=1024 * 1024)
    finally:
        for part in parts:
            part.unlink(missing_ok=True)

    written = destination.stat().st_size
    if written != size:
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            f"{url} downloaded {written} bytes but Content-Length was {size}."
        )
    return destination


def iowaga_spectral_grid(
    frequency=None, direction=None, n_directions=DEFAULT_N_DIRECTIONS
):
    """Build the `ww3recon.SpectralGrid` the reconstruction runs on.

    The grid is validated here rather than trusted, because `SpectralGrid`
    derives its integration weights from the first two entries alone:
    `df_i = f_i (r - 1/r) / 2` with `r = f[1] / f[0]`, and `dtheta` from
    `theta[1] - theta[0]`. Those are WW3's own rules and exactly right on the
    native ladder, but they are silently wrong on a frequency axis that is not
    geometric or a direction axis that is not uniform -- every moment would
    pick up a systematic error with nothing raising. `frequency` and
    `direction` are public keyword arguments on `spectra_from_partitions`, so
    this checks what it was handed.
    """
    if frequency is None:
        frequency = iowaga_frequencies()
    frequency = np.asarray(frequency, dtype=np.float64)
    if direction is None:
        direction = np.arange(n_directions, dtype=np.float64) * (360.0 / n_directions)
    direction = np.asarray(direction, dtype=np.float64)

    if frequency.size < 2 or direction.size < 2:
        raise ValueError(
            "The spectral grid needs at least two frequencies and two "
            f"directions; got {frequency.size} and {direction.size}."
        )

    ratios = frequency[1:] / frequency[:-1]
    if not np.all(frequency > 0.0) or not np.allclose(ratios, ratios[0], rtol=1e-6):
        raise ValueError(
            "The frequency axis must be a positive geometric ladder -- "
            "ww3recon integrates with WW3's own bin width "
            "df_i = f_i (r - 1/r) / 2, taken from the first two entries, so a "
            "non-geometric axis biases every moment silently. Got ratios "
            f"spanning {ratios.min():.6f} to {ratios.max():.6f}."
        )

    steps = np.diff(direction)
    if not np.allclose(steps, steps[0], rtol=1e-6):
        raise ValueError(
            "The direction axis must be uniformly spaced -- ww3recon takes a "
            "single scalar dtheta from the first two entries. Got steps "
            f"spanning {steps.min():.6f} to {steps.max():.6f} degrees."
        )

    return SpectralGrid(
        f=frequency,
        theta=np.deg2rad(direction),
        direction_convention="from (clockwise from north)",
    )


def significant_height_from_efth(efth, grid):
    """Hs = 4 sqrt(int int E df dtheta) from a (..., f, theta) spectrum.

    Integrates with the same rule the reconstruction normalizes against --
    summation over WW3's geometric bin widths `grid.df`, not a trapezoid over
    the frequency axis. That match matters: ww3recon scales each partition so
    that `(S * df).sum()` reproduces its own `phs`, so checking the result
    with a trapezoid instead would measure the difference between two
    quadrature rules on a 1.1 geometric ladder and report it as a bias in the
    reconstruction.
    """
    density = np.asarray(efth, dtype=np.float64).sum(axis=-1) * grid.dtheta
    m0 = (density * grid.df).sum(axis=-1)
    return 4.0 * np.sqrt(np.clip(m0, 0.0, None))


def verify_hs_against_source(
    efth,
    grid,
    source_hs,
    rtol=HS_CHECK_RTOL,
    min_hs=HS_CHECK_MIN_HS,
):
    """Cross-check the reconstruction against the file's own `hs`.

    Returns diagnostics (written into the output attrs) and raises if the two
    disagree beyond `rtol`. Because the partitions are energy-complete this
    is a genuinely tight check: a wrong field, a mis-indexed partition, or a
    lost swell system all show up here rather than as a quiet bias
    downstream.

    Only points with source Hs above `min_hs` are scored -- at near-zero
    energy the relative error is dominated by rounding.
    """
    reconstructed = significant_height_from_efth(efth, grid)
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
            "IOWAGA partition reconstruction failed its self-check: significant "
            f"height recomputed from the reconstructed spectrum is off by a "
            f"median {median_bias:+.1%} against the file's own `hs` over "
            f"{n_scored} points (tolerance {rtol:.0%}). The partitions are "
            "energy-complete and each one is renormalized to its own `phs`, so "
            "this points at a structural problem -- a renamed field, a "
            "mis-indexed partition, or a lost wave system -- rather than at the "
            "choice of frequency shape family. See "
            "raw_data_access/datasets/iowaga.py."
        )
    return diagnostics


def partition_variable_names(n_partitions=N_PARTITIONS):
    """The variables the reconstruction reads.

    The per-partition shape parameters, plus the three whole-spectrum fields:
    `hs` for the energy-closure diagnostic and the self-check, `t0m1` for the
    peakedness fit, `t02` for the tail-exponent fit.
    """
    names = [
        f"{field}{index}" for field in PARTITION_FIELDS for index in range(n_partitions)
    ]
    return names + [REFERENCE_FIELD, T0M1_FIELD, T02_FIELD]


def spectra_from_partitions(
    ds,
    n_directions=DEFAULT_N_DIRECTIONS,
    frequency=None,
    direction=None,
    windsea_family=DEFAULT_WINDSEA_FAMILY,
    swell_family=DEFAULT_SWELL_FAMILY,
    fit_tail=True,
    n_partitions=N_PARTITIONS,
    check_hs=True,
    point_block=DEFAULT_POINT_BLOCK,
    dtype=np.float32,
):
    """Reconstruct E(f, theta) from a loaded window of partition fields.

    Pure -- no I/O -- so it is unit-testable from a fabricated dataset with
    no network, mirroring how the ERA5 products separate their assembly step.

    The reconstruction itself is Hell's `ww3recon`, vendored at
    `raw_data_access/ww3recon/`. Each partition contributes a normalized
    frequency shape peaked at 1/ptp -- blended between the wind-sea and swell
    families by `pws` rather than hard-switched, so a time series crossing the
    threshold stays continuous -- scaled so its own significant height is
    exactly `phs`, times a cosine-2s lobe on `pdir`/`pspr`. Partitions are
    summed, which makes the assembly label-invariant: partition index swapping
    between neighbouring cells is harmless.

    What this buys over a fixed-shape reconstruction is the peakedness. Two
    shape parameters (wind-sea peakedness and swell width) are fitted per
    point by matching the archive's own `t0m1`, and the high-frequency
    exponent is calibrated in a second stage against `t02`. A fixed gamma = 3.3
    assumes a peak shape; this measures it, per point, against a number the
    hindcast already published.

    Absent partitions (NaN phs or ptp, or zero height) contribute nothing.
    Because the partitions are energy-complete no residual system is
    synthesized -- unlike the ERA5 route, which must invent one.

    Land and ice-masked points, where `t0m1` is NaN, are skipped rather than
    fitted and come back as exact zeros. They are not passed to the fit at
    all: a NaN constraint has no solution, and letting one through would
    poison the chunk-modal tail exponent that neighbouring wet points share.

    Returns a Dataset with exactly ONE data variable, `efth`, on dims
    (time, latitude, longitude, frequency, direction). The single-variable
    part is a hard requirement, not style: forcing/ww3.py::
    _extract_all_stations does `(var_name,) = ds.data_vars`, so a second
    variable breaks the WW3 pipeline with an unpacking error. That is why the
    per-point fit diagnostics are reduced to summary statistics in the attrs
    instead of being emitted as fields.
    """
    # The direction axis is defaulted here rather than read back out of the
    # grid: `SpectralGrid` stores radians, and a degrees -> radians -> degrees
    # round trip puts float noise into the written coordinate (210 comes back
    # as 210.00000000000003). The grid gets the radians; the output coordinate
    # keeps exactly the degrees that were asked for.
    if direction is None:
        direction = np.arange(n_directions, dtype=np.float64) * (360.0 / n_directions)
    direction = np.asarray(direction, dtype=np.float64)
    grid = iowaga_spectral_grid(frequency=frequency, direction=direction)
    frequency = grid.f
    n_directions = direction.size

    dims = ("time", "latitude", "longitude")
    shape = tuple(ds.sizes[d] for d in dims)
    n_points = int(np.prod(shape))

    if T0M1_FIELD not in ds:
        raise KeyError(
            f"`{T0M1_FIELD}` is missing from the window. It is not optional: "
            "the per-point shape fit is solved against the archived Tm-10, and "
            "with no constraint there is nothing to fit. Available: "
            f"{sorted(ds.data_vars)}."
        )

    def _flat(name):
        return np.asarray(ds[name].transpose(*dims).values, dtype=np.float64).reshape(
            n_points
        )

    columns = {field: [] for field in PARTITION_FIELDS}
    used = []
    for index in range(n_partitions):
        names = {field: f"{field}{index}" for field in PARTITION_FIELDS}
        if not all(name in ds for name in names.values()):
            continue
        used.append(index)
        for field, name in names.items():
            columns[field].append(_flat(name))

    if not used:
        raise KeyError(
            "No complete partition found. The reconstruction needs "
            f"{'/'.join(PARTITION_FIELDS)}<i> for at least one i; the window "
            f"has {sorted(ds.data_vars)}."
        )

    stacked = {field: np.stack(values, axis=1) for field, values in columns.items()}
    t0m1 = _flat(T0M1_FIELD)
    t02 = _flat(T02_FIELD) if T02_FIELD in ds else None
    hs = _flat(REFERENCE_FIELD) if REFERENCE_FIELD in ds else None

    # Mirrors PartitionSet.active, so a point is only fitted if it carries
    # something to fit.
    active = (
        np.isfinite(stacked["phs"])
        & (stacked["phs"] > 1e-4)
        & np.isfinite(stacked["ptp"])
    )
    wet = np.isfinite(t0m1) & (t0m1 > 0.0) & active.any(axis=1)

    efth = np.zeros((n_points, frequency.size, n_directions), dtype=dtype)
    diagnostics = {}

    n_wet = int(wet.sum())
    if n_wet:
        config = ReconstructionConfig(
            windsea_family=windsea_family,
            swell_family=swell_family,
            fit_tail=fit_tail,
            chunk_size=point_block,
        )
        reconstructor = Reconstructor(grid, config)
        wet_index = np.flatnonzero(wet)

        collected = {
            key: [] for key in ("fit_residual", "energy_closure", "n_partitions")
        }
        flagged = {
            key: 0
            for key in ("underconstrained_ws", "underconstrained_sw", "low_closure")
        }
        tail_exponents = []

        # Blocked rather than handed over whole: `reconstruct` allocates a
        # dense float64 (n_points, n_freq, n_dir) for its result, which for a
        # multi-month regional window is several GB. Each block is cast down
        # to `dtype` and dropped immediately.
        for lo in range(0, n_wet, point_block):
            block = wet_index[lo : lo + point_block]
            result = reconstructor.reconstruct(
                PartitionSet(
                    phs=stacked["phs"][block],
                    ptp=stacked["ptp"][block],
                    pdir=stacked["pdir"][block],
                    pspr=stacked["pspr"][block],
                    pws=stacked["pws"][block],
                    hs=None if hs is None else hs[block],
                    t0m1=t0m1[block],
                    t02=None if t02 is None else t02[block],
                )
            )
            efth[block] = result["spectrum"].astype(dtype)
            for key in collected:
                collected[key].append(np.asarray(result[key], dtype=np.float64))
            for key in flagged:
                flagged[key] += int(np.asarray(result[key]).sum())
            tail_exponents.append(np.asarray(result["tail_exponent"], dtype=np.float64))

        merged = {k: np.concatenate(v) for k, v in collected.items()}
        tail = np.concatenate(tail_exponents)
        diagnostics = {
            "fit_n_points": n_wet,
            "fit_residual_median": float(np.nanmedian(merged["fit_residual"])),
            "fit_residual_p95": float(np.nanpercentile(merged["fit_residual"], 95)),
            "mean_n_partitions": float(np.nanmean(merged["n_partitions"])),
            "fraction_underconstrained_windsea": flagged["underconstrained_ws"] / n_wet,
            "fraction_underconstrained_swell": flagged["underconstrained_sw"] / n_wet,
            "windsea_family": result["ws_family"],
            "swell_family": result["sw_family"],
            "windsea_shape_parameter": result["ws_param_name"],
            "swell_shape_parameter": result["sw_param_name"],
        }
        if np.isfinite(tail).any():
            diagnostics["tail_exponent_median"] = float(np.nanmedian(tail))
        if hs is not None:
            closure = merged["energy_closure"]
            diagnostics["energy_closure_median"] = float(np.nanmedian(closure))
            diagnostics["fraction_low_energy_closure"] = flagged["low_closure"] / n_wet

    efth = efth.reshape(shape + (frequency.size, n_directions))

    if check_hs and REFERENCE_FIELD in ds:
        diagnostics.update(
            verify_hs_against_source(
                efth, grid, ds[REFERENCE_FIELD].transpose(*dims).values
            )
        )
    elif check_hs:
        diagnostics["hs_check"] = f"skipped -- no `{REFERENCE_FIELD}` in the window"

    provenance = {
        "reconstruction": (
            "ww3recon (M. C. Hell, WHOI, v0.2.0), vendored at "
            "raw_data_access/ww3recon: per-partition frequency shape blended "
            "by the wind-sea fraction, times a cosine-2s directional lobe, "
            "summed over the hindcast's spectral partitions; the two shape "
            "parameters fitted per point against the archived t0m1, and the "
            "tail exponent against t02"
        ),
        "source": "IOWAGA GLOBMULTI_ERA5_GLOBCUR_01 (Ifremer/LOPS) via data-dataref",
        "source_variables": ",".join(
            f"{field}{i}" for field in PARTITION_FIELDS for i in used
        )
        + f",{REFERENCE_FIELD},{T0M1_FIELD}"
        + (f",{T02_FIELD}" if t02 is not None else ""),
        "n_partitions_used": len(used),
        "shape_parameters_fitted": "yes (per point, against t0m1)",
        "tail_exponent_fitted": (
            "yes (against t02)"
            if fit_tail and t02 is not None
            else "no (family default)"
        ),
        "peak_period_is_true_peak": "yes (ptp = period at spectral density maximum)",
        "per_partition_directional_spread": "yes (pspr per partition)",
        "residual_system_synthesized": "no (partitions are energy-complete)",
        "n_directions": int(n_directions),
        "reconstruction_validation": (
            "family defaults selected on four IOWAGA sites for January 1993; "
            "not validated globally or across seasons"
        ),
        **diagnostics,
        **{
            k: v
            for k, v in ds.attrs.items()
            if k in ("title", "area", "WAVEWATCH_III_version_number", "forcing_wind")
        },
    }

    return xr.Dataset(
        {
            "efth": (
                dims + ("frequency", "direction"),
                efth,
                {
                    "units": EFTH_UNITS,
                    "long_name": (
                        "2D wave energy density spectrum reconstructed from "
                        "WAVEWATCH-III spectral partitions"
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
    """Subset one opened monthly file to the requested window.

    The +/- buffer_deg padding matches era5.py's convention and exists for
    the same reason -- a boundary bounding box from
    mom6_forge.Grid.get_bounding_boxes is a near-zero-width strip, which
    would otherwise select zero or one grid points.

    Latitude is sliced with an explicit ascending/descending check rather
    than assuming a direction: xarray's .sel with a slice silently returns
    nothing if the slice runs opposite to the coordinate's order.

    A window crossing the antimeridian is taken as two slices and joined,
    since the longitude axis is monotonic and one slice across the seam
    selects nothing. `mom6_forge.utils.longitude_slicer` would also do this,
    but it rolls the whole array; the file is already local here and the
    two-slice form keeps the intent obvious. The shared
    `convert_lons_to_180_range` IS used, so this agrees with glorys.py on
    longitude convention.
    """
    if normalize_longitudes:
        lon_min, lon_max = convert_lons_to_180_range(lon_min, lon_max)

    ds = ds.sel(time=slice(pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])))

    lat_slice = slice(lat_min - buffer_deg, lat_max + buffer_deg)
    if ds["latitude"].values[0] > ds["latitude"].values[-1]:
        lat_slice = slice(lat_slice.stop, lat_slice.start)
    ds = ds.sel(latitude=lat_slice)

    west, east = lon_min - buffer_deg, lon_max + buffer_deg
    if west < east:
        ds = ds.sel(longitude=slice(west, east))
    else:
        ds = xr.concat(
            [
                ds.sel(longitude=slice(west, 180.0)),
                ds.sel(longitude=slice(-180.0, east)),
            ],
            dim="longitude",
        )

    if ds.sizes.get("latitude", 0) == 0 or ds.sizes.get("longitude", 0) == 0:
        raise ValueError(
            f"No IOWAGA grid points in lat [{lat_min}, {lat_max}] lon "
            f"[{lon_min}, {lon_max}] (buffer {buffer_deg} deg). The "
            f"{GRID_NAME} grid is 0.5 degree, spanning -78 to 83 north."
        )
    return ds


class IOWAGA(WW3ForcingProduct):
    product_name = "iowaga"
    description = (
        "IOWAGA GLOBMULTI_ERA5_GLOBCUR_01 wave hindcast (Ifremer/LOPS): "
        "WAVEWATCH-III v7.08 with Alday et al. (2021) physics, ERA5 winds and "
        "CMEMS-GLOBCURRENT currents, 0.5 degree global, 3-hourly, 1993 to "
        "present. Supplies WW3 boundary spectra E(f, theta) reconstructed "
        "from the hindcast's six-way spectral partitioning -- each partition "
        "on its own true peak period, its own directional spread and its own "
        "wind-sea fraction, with the peak shape fitted per point against the "
        "archived t0m1 rather than assumed. The partitions are "
        "energy-complete, so total significant height is reproduced without "
        "synthesizing a residual system."
    )
    link = "https://doi.org/10.12770/857a3337-f59a-481a-bf98-5561e8b61e7b"
    time_var_name = "time"
    time_units = "hours"
    calendar = GREGORIAN

    @classmethod
    def validate_method(cls, method_name, **kwargs):
        """Not auto-validatable: it needs the live Ifremer file server.

        docs/source/raw_data_access/check_raw_data.py calls
        ProductRegistry.validate_function on every registered product from a
        nightly runner. A toy call here would download a 2.8 GB monthly file
        from a third-party server, so the nightly job's result would track
        Ifremer's uptime and burn bandwidth. Return False, which is what
        BaseProduct.validate_method returns on error anyway.
        """
        cls.logger.info(
            "%s cannot be auto-validated: it downloads ~2.8 GB monthly files "
            "from data-dataref.ifremer.fr.",
            cls.product_name,
        )
        return False

    @accessmethod(
        description=(
            "Downloads IOWAGA GLOBMULTI_ERA5_GLOBCUR_01 monthly field files "
            "and reconstructs a 2D wave spectrum E(f, theta) from their "
            "six-way spectral partitioning, in the same (time, latitude, "
            "longitude, frequency, direction) shape as the ERA5 wave-spectra "
            "products -- so it is a drop-in replacement for them. No API key."
        ),
        type="python",
        how_to_use=(
            "Set ww3_obc_product_name='iowaga' and "
            "ww3_obc_function_name='get_iowaga_2d_spectra' on "
            "WW3Configurator. Needs outbound HTTPS to "
            "data-dataref.ifremer.fr and no credentials. Each month of the "
            "requested range is downloaded (~2.8 GB), subset, and deleted "
            "before the next, so peak transient disk is one file; pass "
            "keep_raw=True to retain them. Knobs (n_directions, "
            "windsea_family, swell_family, fit_tail, buffer_deg, n_chunks, "
            "raw_folder, keep_raw, check_hs, point_block) go through "
            "WW3Configurator's ww3_obc_extra_args."
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
        n_directions=DEFAULT_N_DIRECTIONS,
        windsea_family=DEFAULT_WINDSEA_FAMILY,
        swell_family=DEFAULT_SWELL_FAMILY,
        fit_tail=True,
        buffer_deg=1.0,
        n_chunks=DEFAULT_N_CHUNKS,
        raw_folder=None,
        keep_raw=False,
        check_hs=True,
        point_block=DEFAULT_POINT_BLOCK,
        normalize_longitudes=True,
    ):
        # `variables` exists only to satisfy ForcingProduct.required_args. It
        # cannot select what gets read: the reconstruction always needs the
        # full partition set, and forcing/ww3.py calls the shared OBC engine
        # with a hardcoded variables=[], so honouring it would mean reading
        # nothing on every real pipeline call.
        if variables:
            raise ValueError(
                "iowaga does not take a `variables` list -- the reconstruction "
                "always needs the full partition set "
                f"({'/'.join(PARTITION_FIELDS)}0-{N_PARTITIONS - 1}) plus "
                f"`{REFERENCE_FIELD}`, `{T0M1_FIELD}` and `{T02_FIELD}`. "
                f"Got variables={variables!r}."
            )

        check_coverage(dates)

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        staging = Path(raw_folder) if raw_folder else output_folder / "iowaga_raw"
        staging.mkdir(parents=True, exist_ok=True)

        wanted = partition_variable_names()
        windows = []
        for year, month in months_in_range(dates):
            url = build_month_url(year, month)
            raw_path = staging / Path(url).name
            download_month(url, raw_path, n_chunks=n_chunks)
            try:
                with xr.open_dataset(raw_path) as monthly:
                    missing = [v for v in wanted if v not in monthly.data_vars]
                    if missing:
                        raise KeyError(
                            f"{raw_path.name} is missing {missing}, which the "
                            "partition reconstruction needs. Available: "
                            f"{sorted(monthly.data_vars)}."
                        )
                    window = _select_window(
                        monthly[wanted],
                        dates=dates,
                        lat_min=lat_min,
                        lat_max=lat_max,
                        lon_min=lon_min,
                        lon_max=lon_max,
                        buffer_deg=buffer_deg,
                        normalize_longitudes=normalize_longitudes,
                    )
                    if window.sizes.get("time", 0):
                        windows.append(window.load())
            finally:
                # One month on disk at a time, so a multi-year request does
                # not accumulate ~2.8 GB per month of staging.
                if not keep_raw:
                    raw_path.unlink(missing_ok=True)

        if not windows:
            raise ValueError(
                f"No IOWAGA time steps between {dates[0]} and {dates[-1]}."
            )
        combined = windows[0] if len(windows) == 1 else xr.concat(windows, dim="time")

        spectra = spectra_from_partitions(
            combined,
            n_directions=n_directions,
            windsea_family=windsea_family,
            swell_family=swell_family,
            fit_tail=fit_tail,
            check_hs=check_hs,
            point_block=point_block,
        )
        spectra.to_netcdf(
            output_path, encoding={"efth": {"zlib": True, "complevel": 1}}
        )
        if not keep_raw:
            try:
                staging.rmdir()  # only if it is now empty
            except OSError:
                pass
        return output_path
