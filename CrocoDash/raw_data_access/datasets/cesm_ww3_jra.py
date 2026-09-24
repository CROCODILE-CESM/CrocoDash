"""
Data Access Module -> CESM-WW3-JRA (global WAVEWATCH III spectral database)

Serves full 2D wave spectra E(f, theta) for a regional case's open boundaries
out of a JRA-forced, global, wave-only CESM/WW3 run's 6-hourly netCDF
restarts. It is the third `ww3_obc_product_name` option alongside
`reference_waves` (synthetic, reference.py) and `era5_wave_spectra`
(CDS/ECMWF, era5.py), and unlike either of those it needs no network access
and no credentials -- just read access to the run directory on GLADE.

Why it exists: the regional cases this feeds are themselves JRA-forced, so
their boundary spectra come from the same winds that drive their interior,
which ERA5 cannot offer. The default database was produced by
`wi_jra.glo1p0.001`, a 1-degree global WW3 run (grid `ww3glo1p0`, 360x160,
cyclic in x) started cold on 2018-11-01, whose useful record therefore begins
about 2018-12-01, after 2-4 weeks of spin-up.

What this module does NOT do is any physics: a WW3 restart already holds the
full spectrum. The work is reading it out in the right shape, and the five
conventions that takes were read out of WW3/model/src rather than guessed:

  1. `va` index order    `kk = (ik-1)*nth + ith`  -- frequency-major, so the
                         600 va variables reshape to (nk, nth)
                         (wav_restart_mod.F90:190-197, w3gridmd.F90:1334,
                         ww3_bounc.F90:643)
  2. frequency axis      `f_k = FR1 * XFR**(k-1)`, Hz (w3gridmd.F90:1313)
  3. `va` is ACTION      `E(f,th) = va * 2*pi*sigma / Cg(f, depth)`, giving
                         m2 s rad-1 (w3iopomd.F90:1231-1240)
  4. direction axis      WW3's internal TH is Cartesian, CCW from east,
                         direction-of-propagation; what a spectrum file
                         carries is `mod(450 - th_deg, 360)`, i.e. the
                         nautical "to" direction (ww3_ounp.F90:3245, the
                         exact inverse of ww3_bounc.F90:581). Hence
                         `direction_convention = DIRECTION_TO` below -- this
                         is the one product of the three that is certain
                         about its convention, because both ends of it are
                         the same code base.
  5. direction ORDER     keep WW3's own index order (90, 75, ..., 0, 345,
                         ..., 105 -- descending, then wrapping, so not
                         monotonic). ww3_bounc sets SPCONV from THETA(1) vs
                         TH(1) (ww3_bounc.F90:629); that order makes it
                         False and the copy bit-exact. Sorting the axis
                         ascending would flip SPCONV to True and force a
                         needless W3CSPC remap.

Those five were then checked numerically, twice. First on the producing
run's own HS history field: Hs rebuilt from `va0001..va0600` matched it to a
max absolute error of 0.0001 m over 3991 wet points. Then end to end on what
this module actually emits, over an Agulhas-sized window on 2019-06-05:

  - Hs integrated from the emitted E(f, theta) is 0.984-0.9998 of the Hs the
    same restart gives through WW3's own integration. The deficit is exactly
    the unresolved high-frequency tail, which WW3 adds analytically (FTE)
    and a spectrum file does not carry -- ww3_bounc re-adds its own.
  - The emitted direction axis agrees with the run's exported Stokes drift
    -- which points unambiguously where the waves are going, with no
    convention to argue about -- to a median 23 degrees, against 157 degrees
    for the "coming from" alternative. The axis is "to", as conventions 4
    and 5 say it should be.

Conversion 3 needs the local water depth, which the restart does not carry
(it has `mapsta` but no coordinates and no bathymetry). It comes from the
static MOM6-style topography file that the same grid-generation step wrote
next to the WW3 grid preprocessor inputs -- verified to be exactly the
`<grid>_bottom.inp` that built `mod_def.ww3`, and carrying `min_depth` as a
global attribute. Because the producing run sets
`input%forcing%water_levels = "F"`, WW3's dynamic depth equals that static
bathymetry exactly, so this is not an approximation. It would stop being
exact for a database whose run turns water levels on.

Calendar: the database runs NO_LEAP, because its own JRA v1.5 forcing only
exists as a noleap dataset, while the regional cases that consume it run
GREGORIAN. Every date is labelled correctly on both sides except that the
database has no `YYYY-02-29` at all. A request covering one is served
`YYYY-02-28`'s spectra for the matching time of day and stamped with the
requested 02-29, so the consumer sees an unbroken gregorian series. Repeating
02-28 rather than interpolating across the gap is deliberate: a repeated day
is a self-consistent sea state, where blending 02-28 and 03-01 bin by bin can
produce a spectrum that matches neither.

Sea ice is why land is marked as NaN rather than as zero. A cell that WW3 has
iced over carries exactly zero energy in every bin, and at high latitudes a
whole boundary can be like that: the north edge of a Bering Sea domain at
67 N is all zero every January and carries real spectra again by August. That
is a valid boundary condition -- no wave energy enters through ice -- and it
has to reach ww3_bounc as real zero-valued stations, not be mistaken for land
and dropped, which would leave ww3_bounc extrapolating swell into the ice
from open water hundreds of kilometres south.

Two caveats that belong to the database, not to this reader, and that matter
when judging the spectra it serves:

  - The producing run has stub ocean (SOCN), so no currents and therefore no
    current-wave refraction. That matters most in exactly the places a strong
    boundary current crosses a domain edge.
  - Its sea ice is DICE%SSMI, a CLIMATOLOGY rather than observed
    interannual ice. The ice edge is therefore climatological: fine for
    mid-latitude domains, a real caveat for polar ones.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from CrocoDash.raw_data_access.base import *

logger = setup_logger(__name__)

# The production database and the static geometry of the grid it was run on.
# Both are overridable per call (via configure_forcings's
# ww3_obc_function_overrides) so that any other CESM/WW3 run with 6-hourly
# netCDF restarts -- e.g. the 0.5-degree `wi_jra.glo0p5.001` sibling -- can be
# read by the same code.
_DEFAULT_DATABASE_ROOT = "/glade/derecho/scratch/altuntas/wi_jra.glo1p0.001/run"
_DEFAULT_GRID_FILE = (
    "/glade/derecho/scratch/altuntas/croc_input/ww3glo1p0/wav/ocean_topog_ww3glo1p0.nc"
)

# Spectral discretization of the default database's grid, from the
# `XFR FR1 NK NTH RTH0` line of its ww3_grid.inp (`1.1  0.04118  25  24  0.0`).
# NK/NTH are NOT here: they are read from each restart's own `nk`/`nth`
# variables, so a mismatch shows up as data rather than as a silent reshape.
_DEFAULT_FR1 = 0.04118
_DEFAULT_XFR = 1.1
_DEFAULT_DIRECTION_OFFSET = 0.0

# Restarts are written every 6 hours, on the hour, starting at 00Z.
_RESTART_HOURS = (0, 6, 12, 18)

_GRAVITY = 9.806  # w3gridmd.F90's GRAV, not 9.81 -- keeps Cg consistent with WW3


def spectral_axes(
    nk,
    nth,
    fr1=_DEFAULT_FR1,
    xfr=_DEFAULT_XFR,
    direction_offset=_DEFAULT_DIRECTION_OFFSET,
):
    """Build a WW3 grid's frequency and direction axes from its five spectral
    parameters. Pure, so the conventions above are testable without a restart.

    Returns
    -------
    frequency : (nk,) float64, Hz -- ``fr1 * xfr**(k-1)``.
    sigma : (nk,) float64, rad s-1 -- ``2*pi*frequency``, needed by
        `group_velocity` and `action_to_energy`.
    direction : (nth,) float64, degrees, nautical "to" convention, in WW3's
        own (non-monotonic) index order -- see conventions 4 and 5 in the
        module docstring.
    """
    frequency = fr1 * xfr ** np.arange(nk, dtype=np.float64)
    sigma = 2.0 * np.pi * frequency

    # w3gridmd.F90:1276 -- th(ith) = dth*(rth0 + ith-1), radians CCW from east.
    dth_deg = 360.0 / nth
    th_deg = dth_deg * (direction_offset + np.arange(nth, dtype=np.float64))
    direction = np.mod(450.0 - th_deg, 360.0)

    return frequency, sigma, direction


def group_velocity(sigma, depth, gravity=_GRAVITY):
    """Linear-theory group velocity Cg(sigma, depth), m s-1.

    Solves ``sigma**2 = g*k*tanh(k*d)`` for the wavenumber by Newton
    iteration from a deep-water first guess, then
    ``Cg = 0.5*sigma/k * (1 + 2kd/sinh(2kd))``.

    Parameters
    ----------
    sigma : (nk,) radian frequencies.
    depth : (...,) water depths, m, strictly positive.

    Returns
    -------
    (..., nk) group velocities.
    """
    sigma = np.asarray(sigma, dtype=np.float64)
    depth = np.asarray(depth, dtype=np.float64)[..., None]

    # kd reaches ~3000 for the shortest bin over abyssal depths, which
    # overflows cosh/sinh in float64. Every kd-dependent term below has
    # already saturated to its deep-water limit long before kd = 50
    # (tanh 50 = 1 to machine precision, 2kd/sinh(2kd) < 1e-40), so
    # clamping changes no digit of the answer and keeps the arithmetic
    # finite instead of leaning on inf propagating the right way.
    kd_max = 50.0

    k = np.broadcast_to(sigma**2 / gravity, depth.shape[:-1] + sigma.shape).copy()
    for _ in range(60):
        kd = np.minimum(k * depth, kd_max)
        f = gravity * k * np.tanh(kd) - sigma**2
        fp = gravity * (np.tanh(kd) + kd / np.cosh(kd) ** 2)
        k -= f / fp

    kd = np.minimum(k * depth, kd_max)
    return 0.5 * sigma / k * (1.0 + 2.0 * kd / np.sinh(2.0 * kd))


def action_to_energy(va, sigma, cg):
    """Convert WW3's stored action density to variance density E(f, theta).

    ``E = va * 2*pi*sigma / Cg`` (w3iopomd.F90:1231-1240), m2 s rad-1.

    Parameters
    ----------
    va : (..., nk, nth) action density as stored in the restart.
    sigma : (nk,) radian frequencies.
    cg : (..., nk) group velocities, broadcastable against ``va``'s leading
        dimensions.
    """
    factor = 2.0 * np.pi * np.asarray(sigma, dtype=np.float64) / np.asarray(cg)
    return np.asarray(va, dtype=np.float64) * factor[..., None]


def requested_timestamps(dates):
    """Every 6-hourly restart stamp of every whole day in ``dates``.

    Whole-day inclusive on both ends: a plain ``date_range(..., freq="6h")``
    would stop at the last day's 00:00 and drop its 06/12/18Z steps, so the
    end day is extended to 18:00 first. Same "every step of every requested
    day" convention reference.py and era5.py use, which is also what obc.py's
    filename-based coverage check assumes.
    """
    days = pd.date_range(
        pd.Timestamp(dates[0]).normalize(),
        pd.Timestamp(dates[-1]).normalize(),
        freq="D",
    )
    if len(days) == 0:
        raise ValueError(f"No whole days in requested range {dates[0]}..{dates[-1]}.")
    return pd.date_range(
        days[0], days[-1] + pd.Timedelta(hours=_RESTART_HOURS[-1]), freq="6h"
    )


def restart_filename(case_name, stamp):
    """Name of the restart holding ``stamp``, applying the NO_LEAP mapping.

    The database has no 29 February (see the module docstring), so a
    gregorian 02-29 is served by 02-28's file at the same time of day. Every
    other date maps to its own label.
    """
    stamp = pd.Timestamp(stamp)
    if (stamp.month, stamp.day) == (2, 29):
        stamp = stamp.replace(day=28)
    seconds = stamp.hour * 3600 + stamp.minute * 60 + stamp.second
    return f"{case_name}.ww3.r.{stamp:%Y-%m-%d}-{seconds:05d}.nc"


def discover_case_name(database_root):
    """Infer the CESM case name from the restarts in ``database_root``.

    Restarts are named ``<case>.ww3.r.<date>-<seconds>.nc``, so the case name
    is everything before the first ``.ww3.r.``. Inferring it beats making the
    caller repeat a name that is already written on every file in the
    directory, and a directory holding more than one case is ambiguous enough
    to be worth refusing outright.
    """
    database_root = Path(database_root)
    if not database_root.is_dir():
        raise FileNotFoundError(f"WW3 database directory not found: {database_root}")
    names = {p.name.split(".ww3.r.")[0] for p in database_root.glob("*.ww3.r.*.nc")}
    if not names:
        raise FileNotFoundError(
            f"No WW3 restart files (*.ww3.r.*.nc) found in {database_root}."
        )
    if len(names) > 1:
        raise ValueError(
            f"{database_root} holds restarts from more than one case ({sorted(names)}); "
            "pass case_name explicitly."
        )
    return names.pop()


def available_range(database_root, case_name):
    """(first, last) restart timestamp present in the database, as Timestamps.

    Read from filenames, not from the files. The producing run may still be
    advancing, so this is deliberately re-read on every call rather than
    baked into the product metadata as a fixed end date.
    """
    stamps = []
    for path in Path(database_root).glob(f"{case_name}.ww3.r.*.nc"):
        label = path.name[len(f"{case_name}.ww3.r.") : -len(".nc")]
        date_part, _, seconds_part = label.rpartition("-")
        try:
            stamps.append(
                pd.Timestamp(date_part) + pd.Timedelta(seconds=int(seconds_part))
            )
        except ValueError:
            continue
    if not stamps:
        raise FileNotFoundError(
            f"No parseable WW3 restarts for case '{case_name}' in {database_root}."
        )
    return min(stamps), max(stamps)


def _axis_indices(coord, lo, hi, cyclic, n):
    """Index range covering [lo, hi] on a regular 1-D axis.

    Returns an integer array of (possibly out-of-range, for a cyclic axis)
    indices; the caller mods them into the array and keeps the unmodded
    values for the coordinate, so a window crossing the seam stays monotonic
    in longitude instead of jumping 359.5 -> 0.5.
    """
    origin, delta = coord[0], coord[1] - coord[0]
    i0 = int(np.floor((lo - origin) / delta))
    i1 = int(np.ceil((hi - origin) / delta))
    if not cyclic:
        i0, i1 = max(i0, 0), min(i1, n - 1)
        if i1 < i0:
            raise ValueError(
                f"Requested range {lo}..{hi} lies entirely outside the database "
                f"axis {coord[0]}..{coord[-1]}."
            )
    elif i1 - i0 + 1 >= n:
        i0, i1 = 0, n - 1
    return np.arange(i0, i1 + 1)


def _window_runs(j_idx, i_idx, nx):
    """Row bounds and contiguous column runs of a lat/lon window.

    Returns ``(j0, j1, wrapped, runs)``: the row slice, the column indices
    modded into the array, and the positions in ``wrapped`` that form each
    contiguous run -- one hyperslab per run, so a window crossing the cyclic
    seam is read as a handful of slabs rather than a fancy-indexed read.
    """
    j0, j1 = int(j_idx[0]), int(j_idx[-1]) + 1
    wrapped = np.mod(i_idx, nx)
    breaks = np.flatnonzero(np.diff(wrapped) != 1) + 1
    runs = np.split(np.arange(len(wrapped)), breaks)
    return j0, j1, wrapped, runs


def _read_window(path, spec_count, j_idx, i_idx, nx):
    """Read every ``vaNNNN`` over one lat/lon window of one restart.

    Returns (nj, ni, spec_count) with the restart's `_FillValue` decoded to
    NaN. A window crossing the cyclic seam is read as contiguous runs and
    reassembled, because a strided/fancy netCDF read of 600 variables is
    much slower than a handful of hyperslabs.
    """
    j0, j1, wrapped, runs = _window_runs(j_idx, i_idx, nx)

    out = np.empty((len(j_idx), len(i_idx), spec_count), dtype=np.float32)
    with Dataset(path) as nc:
        for s in range(spec_count):
            var = nc.variables[f"va{s + 1:04d}"]
            for run in runs:
                c0, c1 = int(wrapped[run[0]]), int(wrapped[run[-1]]) + 1
                block = var[0, j0:j1, c0:c1]
                out[:, run[0] : run[-1] + 1, s] = np.ma.filled(block, np.nan)
    return out


def _read_mapsta_window(path, j_idx, i_idx, nx):
    """The restart's own wet mask over the window, as a boolean (nj, ni).

    The restart mask -- not the grid file's -- is authoritative: ww3_grid
    drops points it considers isolated (274 of them on `ww3glo1p0`), and
    those are land as far as the spectra are concerned.

    Wet means unmasked AND positive, matching WW3's own MAPSTA convention
    (0 land or excluded, 1 sea, 2 active boundary, negative temporarily
    disabled). On the default database the restart only ever writes 1 or its
    fill value, but reading the sign rather than just the mask is what the
    convention actually says.
    """
    j0, j1, wrapped, runs = _window_runs(j_idx, i_idx, nx)

    out = np.zeros((len(j_idx), len(i_idx)), dtype=bool)
    with Dataset(path) as nc:
        var = nc.variables["mapsta"]
        for run in runs:
            c0, c1 = int(wrapped[run[0]]), int(wrapped[run[-1]]) + 1
            block = var[0, j0:j1, c0:c1]
            valid = ~np.ma.getmaskarray(block)
            out[:, run[0] : run[-1] + 1] = valid & (np.ma.filled(block, 0) > 0)
    return out


def _read_static_grid(grid_file):
    """Longitude/latitude axes, depth and min_depth from the database's grid.

    The file is the MOM6-style topography written alongside the WW3 grid
    preprocessor inputs; its `depth` was verified identical to the
    `<grid>_bottom.inp` that actually built `mod_def.ww3`.

    Rectilinearity is asserted rather than assumed: the index arithmetic in
    `_axis_indices`, and emitting 1-D `latitude`/`longitude` coordinates at
    all, both depend on it. A curvilinear global WW3 grid would need a
    search instead, and should fail loudly here rather than silently pick
    the wrong cells.

    `min_depth` floors the depth fed to `group_velocity`, which needs it
    strictly positive: a depth near zero makes Cg tiny and the converted
    energy overflow float32 to inf. A grid file whose `min_depth` is missing
    or not positive falls back to its shallowest wet depth, with a warning.
    Zero is common: the tutorial builds its Topo with min_depth=0, and
    Topo.from_topo_file defaults to it. The default grid carries 10.0.
    """
    with xr.open_dataset(grid_file) as ds:
        x = ds["x"].values
        y = ds["y"].values
        depth = ds["depth"].values
        min_depth = ds.attrs.get("min_depth")

    if min_depth is None or not float(min_depth) > 0:
        wet_depths = depth[depth > 0]
        if wet_depths.size == 0:
            raise ValueError(f"{grid_file} has no positive depth anywhere.")
        logger.warning(
            "%s has min_depth=%s; using its shallowest wet depth, %s m, as "
            "the floor for the group velocity.",
            grid_file,
            min_depth,
            float(wet_depths.min()),
        )
        min_depth = wet_depths.min()
    min_depth = float(min_depth)

    if not (np.allclose(x, x[0][None, :]) and np.allclose(y, y[:, 0][:, None])):
        raise ValueError(
            f"{grid_file} is not rectilinear; this reader's index arithmetic "
            "assumes a regular lat/lon WW3 grid."
        )
    return x[0], y[:, 0], depth, min_depth


class CESM_WW3_JRA(WW3ForcingProduct):
    product_name = "CESM-WW3-JRA"
    description = (
        "Full 2D wave spectra E(f, theta) for WW3 open boundaries, read out "
        "of a JRA-forced global wave-only CESM/WW3 run's 6-hourly netCDF "
        "restarts on GLADE -- boundary waves driven by the same JRA winds "
        "as the regional case's own interior, with no network access or "
        "credentials required. The default database is the 1-degree "
        "`wi_jra.glo1p0.001` run (useful record from ~2018-12-01, after "
        "spin-up)."
    )
    link = "https://github.com/CROCODILE-CESM/CrocoDash"
    # The output carries real gregorian datetime64 stamps: the NO_LEAP -> real
    # calendar mapping happens in the reader (see module docstring), so what
    # leaves this product is already on the consumer's calendar.
    time_var_name = "time"
    time_units = "hours"
    calendar = GREGORIAN
    # Certain, not inherited: both ends of this convention are the same code
    # base -- see convention 4 in the module docstring.
    direction_convention = DIRECTION_TO
    # WW3's own mapsta tells land from sea, so land is marked unambiguously
    # rather than by being zero -- which here means a real, becalmed or
    # ice-covered sea point. See the ice note in the module docstring.
    land_marker = LAND_NAN

    @classmethod
    def validate_method(cls, method_name, **kwargs):
        # The generic toy dates (2000) predate the database.
        return super().validate_method(
            method_name, **{"dates": ["2019-01-01", "2019-01-01"], **kwargs}
        )

    @accessmethod(
        description=(
            "Reads 2D wave spectra for a boundary window out of a global "
            "CESM/WW3 run's 6-hourly netCDF restarts, converting WW3's "
            "stored action density to variance density E(f, theta) and "
            "writing a NetCDF file with real (time, latitude, longitude, "
            "frequency, direction) dims -- the same shape era5.py's decoded "
            "product has, so the rest of the WW3 OBC pipeline is unchanged. "
            "Needs no credentials, only read access to the run directory."
        ),
        type="python",
        how_to_use=(
            "Requires read access to `database_root` (a CESM/WW3 run "
            "directory of *.ww3.r.*.nc restarts) and `grid_file` (the "
            "MOM6-style topography of the grid that run used). Both default "
            "to the 1-degree `wi_jra.glo1p0.001` database on GLADE, whose "
            "useful record starts about 2018-12-01 and grows as the run "
            "advances. Point them elsewhere via configure_forcings's "
            "`ww3_obc_function_overrides` to read another CESM/WW3 run -- "
            "e.g. the 0.5-degree `wi_jra.glo0p5.001` sibling, which also "
            "needs its own `fr1`/`xfr` if its ww3_grid.inp differs."
        ),
    )
    def get_cesm_ww3_jra_spectra(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="cesm_ww3_jra_spectra.nc",
        variables=None,
        database_root=_DEFAULT_DATABASE_ROOT,
        grid_file=_DEFAULT_GRID_FILE,
        case_name=None,
        fr1=_DEFAULT_FR1,
        xfr=_DEFAULT_XFR,
        direction_offset=_DEFAULT_DIRECTION_OFFSET,
        buffer_deg=1.5,
        min_stations=2,
        max_buffer_deg=10.0,
    ):
        """Extract a boundary window's spectra and write them as NetCDF.

        `variables` is unused -- a WW3 restart's 600 `va` variables already
        are the whole spectrum -- and is kept only to satisfy
        ForcingProduct's required_args contract.

        `buffer_deg` pads the requested box before indexing. Some padding is
        not optional here: a boundary's box from
        mom6_forge.Grid.get_bounding_boxes is a near-zero-width strip (a
        "north" boundary spans the domain's longitudes at essentially one
        latitude), and on a 1-degree database such a strip can contain no
        cell centre at all. If fewer than `min_stations` wet cells fall in
        the padded window, the padding grows by one degree at a time up to
        `max_buffer_deg` before giving up -- ww3_bounc blends boundary
        points from whatever stations it is given by inverse distance, so
        two real neighbours beat one exact-but-lonely hit.

        Returns the written NetCDF path.
        """
        case_name = case_name or discover_case_name(database_root)
        first, last = available_range(database_root, case_name)
        stamps = requested_timestamps(dates)

        if stamps[0] < first or stamps[-1] > last:
            raise ValueError(
                f"Requested {stamps[0]:%Y-%m-%d %H:%M} .. {stamps[-1]:%Y-%m-%d %H:%M} "
                f"but database '{case_name}' covers "
                f"{first:%Y-%m-%d %H:%M} .. {last:%Y-%m-%d %H:%M}. Note the run "
                "starts cold, so its first few weeks are spin-up and should not "
                "be used as forcing."
            )

        lons, lats, depth, min_depth = _read_static_grid(grid_file)
        ny, nx = depth.shape

        # Put the request on the database's longitude branch, and keep the
        # window's own longitudes unwrapped so they stay monotonic across the
        # seam (forcing/ww3.py::_wrap_lons_like puts them back on the
        # supergrid's branch afterwards).
        # Keep the requested span rather than rebuilding it from two wrapped
        # ends: 0.1..360.1 or -10..360 is a full turn although its ends wrap
        # onto (nearly) the same longitude, and _axis_indices clamps anything
        # that wide to the whole axis. The window always runs eastward from
        # lon_min, so a descending pair wraps: 350..10 crosses the seam
        # (20 degrees), 100..10 reads 270.
        lo = lon_min % 360.0
        span = lon_max - lon_min
        if span < 0:
            span %= 360.0
        hi = lo + span

        paths = [Path(database_root) / restart_filename(case_name, s) for s in stamps]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"{len(missing)} restart(s) missing from {database_root}, first: "
                f"{missing[0].name}. The database may have a gap."
            )

        with Dataset(paths[0]) as nc:
            restart_shape = nc.variables["mapsta"].shape[-2:]
            nk = int(nc.variables["nk"][...])
            nth = int(nc.variables["nth"][...])
        if restart_shape != depth.shape:
            raise ValueError(
                f"Restarts in {database_root} are {restart_shape[0]}x"
                f"{restart_shape[1]} (ny x nx) but grid_file {grid_file} is "
                f"{ny}x{nx}. Point grid_file at the topography of the WW3 grid "
                "that produced the restarts."
            )
        spec_count = nk * nth

        buffer = float(buffer_deg)
        while True:
            j_idx = _axis_indices(lats, lat_min - buffer, lat_max + buffer, False, ny)
            i_idx = _axis_indices(lons, lo - buffer, hi + buffer, True, nx)
            wet = _read_mapsta_window(paths[0], j_idx, i_idx, nx)
            if wet.sum() >= min_stations or buffer >= max_buffer_deg:
                break
            buffer = min(buffer + 1.0, max_buffer_deg)

        if not wet.any():
            raise ValueError(
                f"No wet database cells within {buffer} degrees of "
                f"[{lat_min}, {lat_max}] x [{lon_min}, {lon_max}] -- the whole "
                "window is land or outside the database's latitude range."
            )

        frequency, sigma, direction = spectral_axes(
            nk, nth, fr1=fr1, xfr=xfr, direction_offset=direction_offset
        )

        # Depth is static and water levels are off in the producing run, so
        # Cg is computed once for the window rather than per timestep.
        window_depth = np.maximum(depth[np.ix_(j_idx, np.mod(i_idx, nx))], min_depth)
        cg = group_velocity(sigma, window_depth)

        efth = np.empty(
            (len(stamps), len(j_idx), len(i_idx), nk, nth), dtype=np.float32
        )
        for t, path in enumerate(paths):
            va = _read_window(path, spec_count, j_idx, i_idx, nx)
            va = va.reshape(len(j_idx), len(i_idx), nk, nth)  # frequency-major
            energy = action_to_energy(va, sigma, cg)
            # Land stays NaN (it is already NaN from the restart's fill value;
            # mapsta is applied too so the two can never disagree). It must
            # NOT be zeroed: a genuine zero here means a sea point carrying no
            # wave energy -- an ice-covered boundary in winter, which is a
            # valid boundary condition and has to survive as a real station.
            energy[~wet] = np.nan
            # A finite float64 can still overflow the float32 store to inf;
            # that is reported below rather than warned about here.
            with np.errstate(over="ignore"):
                efth[t] = energy
            if np.isnan(va[wet]).any():
                raise ValueError(
                    f"{path.name} has fill values at cells the mapsta of "
                    f"{paths[0].name} marks as sea; the restarts disagree on "
                    "the land mask."
                )
            if not np.isfinite(efth[t][wet]).all():
                raise ValueError(
                    f"Wave energy at wet cells of {path.name} is not finite in "
                    "float32: the group velocity is near zero there. Check the "
                    f"depths and min_depth in {grid_file}."
                )

        ds = xr.Dataset(
            {
                "efth": (
                    ("time", "latitude", "longitude", "frequency", "direction"),
                    efth,
                    {"units": "m2 s rad-1"},
                )
            },
            coords={
                "time": stamps,
                "latitude": lats[j_idx],
                "longitude": lons[0] + i_idx * (lons[1] - lons[0]),
                "frequency": ("frequency", frequency, {"units": "s-1"}),
                "direction": (
                    "direction",
                    direction,
                    {
                        "units": "degree",
                        "comment": (
                            "propagating towards, clockwise from true north; "
                            "in WW3's own index order"
                        ),
                    },
                ),
            },
            attrs={
                "source_case": case_name,
                "source_database": str(database_root),
                "source_grid": str(grid_file),
                "source_calendar": "noleap (mapped onto the real calendar here)",
            },
        )

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        ds.to_netcdf(output_path)
        ds.close()
        return output_path
