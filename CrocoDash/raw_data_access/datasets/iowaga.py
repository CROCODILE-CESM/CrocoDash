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
wind sea, 1-5 are swell systems ordered by energy -- with four fields each
that are exactly what a parametric reconstruction needs:

    phs0-5   significant height of the partition          m
    ptp0-5   PEAK period of the partition                 s
    pdir0-5  mean direction, coming-from, cw from north   degree
    pspr0-5  directional spread of the partition          degree

Each partition becomes a JONSWAP frequency shape peaked at 1/ptp, scaled so
its significant height is exactly phs, multiplied by a cosine-2s directional
lobe centred on pdir with spread pspr. The partitions are then summed.

Two things make this materially better than the equivalent reconstruction
from ERA5 bulk statistics (`era5_wave_stats.py`):

  * `ptp` is a true peak period -- its standard_name is
    `sea_surface_wave_period_at_variance_spectral_density_maximum` -- which
    is exactly the parameter JONSWAP's peak frequency wants. The ERA5 route
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

What is still assumed: the frequency SHAPE within each partition is JONSWAP
rather than observed. Significant height, peak period and mean direction are
reproduced by construction; the spectral shape between them is parametric.
`spectra_from_partitions` cross-checks the result against the file's own `hs`
on every real call -- see `verify_hs_against_source`.

Cost, and why the whole file comes down
----------------------------------------
The monthly global files are ~2.8 GB and the 25 variables used here are 29%
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

FILE_SERVER_BASE = "https://data-dataref.ifremer.fr/ww3/GLOBMULTI_ERA5_GLOBCUR_01"
GRID_NAME = "GLOB-30M"

# Earliest month published. The end is deliberately NOT hardcoded -- the
# hindcast is extended over time (2026-03 was the last month available on
# 2026-09-10), so `available_months` reads the server's own directory listing
# instead of going stale.
DATASET_START = "1993-01-01T00:00:00"

N_PARTITIONS = 6
PARTITION_FIELDS = ("phs", "ptp", "pdir", "pspr")
# `hs` is fetched too, purely so verify_hs_against_source has an independent
# reference; it takes no part in the reconstruction.
REFERENCE_FIELD = "hs"

# IOWAGA's native spectral discretization, read off its own point-output
# spectra files: 36 frequencies, f0 = 0.0339 Hz, geometric ratio 1.1, and 24
# directions. Reconstructing onto the same grid the real spectral product
# uses means ww3_bounc's SPCONV remapping has the least work to do.
IOWAGA_F0 = 0.0339
IOWAGA_FREQUENCY_RATIO = 1.1
IOWAGA_N_FREQUENCIES = 36
DEFAULT_N_DIRECTIONS = 24

# JONSWAP peak-enhancement factor. 3.3 is the mean value from the original
# JONSWAP fit and the same default era5_wave_stats.py uses, so the two
# products' reconstructions differ in their inputs rather than their shape
# assumption.
DEFAULT_GAMMA = 3.3
# JONSWAP spectral width parameters either side of the peak (Hasselmann 1973).
JONSWAP_SIGMA_BELOW = 0.07
JONSWAP_SIGMA_ABOVE = 0.09

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


def jonswap_shape(frequency, peak_frequency, gamma=DEFAULT_GAMMA):
    """Unnormalized JONSWAP frequency shape, broadcast over `peak_frequency`.

    Returns shape peak_frequency.shape + (n_frequency,). The scale factor is
    left out entirely because the caller renormalizes to a known significant
    height, so alpha and g would cancel; only the shape matters here.

    Guarded with `np.errstate` and finished with `nan_to_num` because absent
    partitions arrive as NaN peak frequencies, which must come back as a row
    of zeros rather than propagating into the sum.
    """
    frequency = np.asarray(frequency, dtype=np.float64)
    fp = np.asarray(peak_frequency, dtype=np.float64)[..., None]
    f = frequency.reshape((1,) * (fp.ndim - 1) + (frequency.size,))

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        pierson = np.power(f, -5.0) * np.exp(-1.25 * np.power(fp / f, 4.0))
        sigma = np.where(f <= fp, JONSWAP_SIGMA_BELOW, JONSWAP_SIGMA_ABOVE)
        exponent = -np.square(f - fp) / (2.0 * np.square(sigma * fp))
        shape = pierson * np.power(gamma, np.exp(exponent))

    return np.nan_to_num(shape, nan=0.0, posinf=0.0, neginf=0.0)


def cosine_2s_spread(direction_deg, mean_direction_deg, spread_deg):
    """Normalized cosine-2s directional distribution D(theta), in rad^-1.

    D(theta) = N * cos^(2s)((theta - theta_m) / 2), with s recovered from the
    circular directional spread by the standard relation for this family,
    sigma^2 = 2 / (s + 1), i.e. s = 2 / sigma^2 - 1 with sigma in radians.

    Computed in log space -- 2s * log(cos(dtheta/2)) with the max subtracted
    before exponentiating -- rather than as a direct power. A narrow swell
    with a spread of a degree or two gives s in the thousands, and
    cos(x)**(2s) evaluated directly underflows to zero in *every* bin
    including the peak, silently producing an all-zero spectrum.

    Normalization is done numerically against the actual direction grid, not
    by the analytic Gamma-function constant, so that sum(D) * dtheta == 1 on
    the discrete bins that get written. That is what makes each partition's
    significant height come out exactly right rather than to within a
    quadrature error.

    NaN (an absent partition, or land) or a non-positive spread yields a
    uniform lobe so those points stay finite; the partition's height is zero
    there anyway, so the choice adds no energy.
    """
    direction = np.deg2rad(np.asarray(direction_deg, dtype=np.float64))
    n_dir = direction.size
    dtheta = 2.0 * np.pi / n_dir

    mean_direction = np.deg2rad(np.asarray(mean_direction_deg, dtype=np.float64))
    spread = np.deg2rad(np.asarray(spread_deg, dtype=np.float64))

    with np.errstate(divide="ignore", invalid="ignore"):
        s = 2.0 / np.square(spread) - 1.0
    degenerate = ~np.isfinite(s) | (s <= 0.0) | ~np.isfinite(mean_direction)
    s = np.where(degenerate, 0.0, s)

    delta = (
        direction.reshape((1,) * mean_direction.ndim + (n_dir,))
        - mean_direction[..., None]
    )
    half = 0.5 * np.where(np.isfinite(delta), delta, 0.0)

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
        return np.where(total > 0.0, lobe / total, 1.0 / (n_dir * dtheta))


def significant_height_from_efth(efth, frequency, n_directions):
    """Hs = 4 sqrt(int int E df dtheta) from a (..., f, theta) spectrum."""
    dtheta = 2.0 * np.pi / n_directions
    m0 = np.trapezoid(np.asarray(efth).sum(axis=-1) * dtheta, x=frequency, axis=-1)
    return 4.0 * np.sqrt(np.clip(m0, 0.0, None))


def verify_hs_against_source(
    efth,
    frequency,
    n_directions,
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
    reconstructed = significant_height_from_efth(efth, frequency, n_directions)
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
            "energy-complete, so this points at a structural problem -- a "
            "renamed field, a mis-indexed partition, or a lost wave system -- "
            "rather than at the JONSWAP shape assumption. See "
            "raw_data_access/datasets/iowaga.py."
        )
    return diagnostics


def partition_variable_names(n_partitions=N_PARTITIONS):
    """The variables the reconstruction reads, plus the `hs` reference."""
    names = [
        f"{field}{index}" for field in PARTITION_FIELDS for index in range(n_partitions)
    ]
    return names + [REFERENCE_FIELD]


def spectra_from_partitions(
    ds,
    n_directions=DEFAULT_N_DIRECTIONS,
    frequency=None,
    direction=None,
    gamma=DEFAULT_GAMMA,
    n_partitions=N_PARTITIONS,
    check_hs=True,
    dtype=np.float32,
):
    """Reconstruct E(f, theta) from a loaded window of partition fields.

    Pure -- no I/O -- so it is unit-testable from a fabricated dataset with
    no network, mirroring how the ERA5 products separate their assembly step.

    Each partition contributes a JONSWAP shape peaked at 1/ptp, renormalized
    so its own significant height is exactly phs, times a cosine-2s lobe on
    pdir/pspr. Absent partitions (NaN phs or ptp, or zero height) contribute
    nothing. Because the partitions are energy-complete no residual system is
    synthesized -- unlike the ERA5 route, which must invent one.

    Returns a Dataset with exactly ONE data variable, `efth`, on dims
    (time, latitude, longitude, frequency, direction). The single-variable
    part is a hard requirement, not style: forcing/ww3.py::
    _extract_all_stations does `(var_name,) = ds.data_vars`, so a second
    variable breaks the WW3 pipeline with an unpacking error.
    """
    frequency = (
        iowaga_frequencies()
        if frequency is None
        else np.asarray(frequency, dtype=np.float64)
    )
    if direction is None:
        direction = np.arange(n_directions, dtype=np.float64) * (360.0 / n_directions)
    direction = np.asarray(direction, dtype=np.float64)
    n_directions = direction.size

    dims = ("time", "latitude", "longitude")
    shape = tuple(ds.sizes[d] for d in dims)
    efth = np.zeros(shape + (frequency.size, n_directions), dtype=np.float64)

    used = []
    for index in range(n_partitions):
        names = {field: f"{field}{index}" for field in PARTITION_FIELDS}
        if not all(name in ds for name in names.values()):
            continue
        used.append(index)

        hs = np.asarray(ds[names["phs"]].transpose(*dims).values, dtype=np.float64)
        tp = np.asarray(ds[names["ptp"]].transpose(*dims).values, dtype=np.float64)
        pdir = np.asarray(ds[names["pdir"]].transpose(*dims).values, dtype=np.float64)
        pspr = np.asarray(ds[names["pspr"]].transpose(*dims).values, dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            peak_frequency = 1.0 / tp
        present = np.isfinite(hs) & (hs > 0.0) & np.isfinite(peak_frequency)
        if not present.any():
            continue

        shape_f = jonswap_shape(frequency, peak_frequency, gamma=gamma)
        # Renormalize each partition to its own Hs: m0 = (hs/4)^2, and the
        # directional lobe integrates to 1, so scaling the frequency shape is
        # enough. Numerical trapezoid over the same grid that gets written,
        # so the height comes back exactly rather than to a tolerance.
        m0_shape = np.trapezoid(shape_f, x=frequency, axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = np.where(m0_shape > 0.0, np.square(hs / 4.0) / m0_shape, 0.0)
        scale = np.where(present, scale, 0.0)
        energy_f = np.nan_to_num(shape_f * scale[..., None])

        lobe = cosine_2s_spread(direction, pdir, pspr)
        efth += energy_f[..., :, None] * lobe[..., None, :]

    if not used:
        raise KeyError(
            "No complete partition found. The reconstruction needs "
            f"{'/'.join(PARTITION_FIELDS)}<i> for at least one i; the window "
            f"has {sorted(ds.data_vars)}."
        )

    diagnostics = {}
    if check_hs and REFERENCE_FIELD in ds:
        diagnostics = verify_hs_against_source(
            efth, frequency, n_directions, ds[REFERENCE_FIELD].transpose(*dims).values
        )
    elif check_hs:
        diagnostics = {"hs_check": f"skipped -- no `{REFERENCE_FIELD}` in the window"}

    provenance = {
        "reconstruction": (
            "per-partition JONSWAP frequency shape x cosine-2s directional "
            "lobe, summed over the hindcast's spectral partitions"
        ),
        "source": "IOWAGA GLOBMULTI_ERA5_GLOBCUR_01 (Ifremer/LOPS) via data-dataref",
        "source_variables": ",".join(
            f"{field}{i}" for field in PARTITION_FIELDS for i in used
        ),
        "n_partitions_used": len(used),
        "gamma": gamma,
        "peak_period_is_true_peak": "yes (ptp = period at spectral density maximum)",
        "per_partition_directional_spread": "yes (pspr per partition)",
        "residual_system_synthesized": "no (partitions are energy-complete)",
        "n_directions": int(n_directions),
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
                efth.astype(dtype),
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
        "a JONSWAP shape on its own true peak period and its own directional "
        "spread. The partitions are energy-complete, so total significant "
        "height is reproduced without synthesizing a residual system."
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
            "keep_raw=True to retain them. Knobs (n_directions, gamma, "
            "buffer_deg, n_chunks, raw_folder, keep_raw, check_hs) go through "
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
        gamma=DEFAULT_GAMMA,
        buffer_deg=1.0,
        n_chunks=DEFAULT_N_CHUNKS,
        raw_folder=None,
        keep_raw=False,
        check_hs=True,
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
                f"`{REFERENCE_FIELD}`. Got variables={variables!r}."
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
            combined, n_directions=n_directions, gamma=gamma, check_hs=check_hs
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
