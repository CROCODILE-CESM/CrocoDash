from pathlib import Path

import numpy as np
import xarray as xr


def write_ww3_boundary_spectrum(file_path, lat, lon, freq, direction, efth, time=None):
    """
    Write a single-point WW3 boundary spectrum file, in the minimal shape
    ww3_bounc.F90 actually reads.

    This is deliberately narrower than a real ww3_ounp point-output file
    (the kind NOAA's own hindcast archive ships): things like station_name,
    frequency1/frequency2 (band edges), depth, u10m/udir, curr/currdir exist
    in that format for CF/GlobWave metadata compliance, but grepping
    ww3_bounc.F90 shows none of them are ever read (no NF90_INQ_VARID call
    for any of them). Only these are:
      - dims/vars "time", "frequency", "direction" (names must match exactly,
        ww3_bounc looks them up by name via NF90_INQ_DIMID/NF90_INQ_VARID)
      - "latitude"/"longitude" (only the first value is ever read into a
        scalar, even if this were made time-varying -- so it's fine as a
        length-1 dim)
      - "efth" (or "Efth" -- ww3_bounc falls back to that capitalization if
        "efth" isn't found)
      - no "station_name" var: if present, ww3_bounc instead reads efth as
        (time, station, frequency, direction) -- but that's not a "multi
        station" capability, it's just a different dimension order for the
        same one-point behavior: that branch's NF90_GET_VAR call hardcodes
        start/count to always read station index 1 only, no matter how many
        stations the file actually declares. Omitting station_name simply
        keeps us on the branch whose dimension order matches what we write
        here, efth(time, frequency, direction, latitude, longitude).

    "_FillValue" on efth is NOT optional the way scale_factor/add_offset
    are: ww3_bounc.F90 calls CHECK_ERR() (a hard EXTCDE(59) exit) right
    after reading it, whereas a missing scale_factor/add_offset is silently
    defaulted to 1./0. (FACTOR=1., OFFSET=0. if the NF90_GET_ATT call fails).
    We write efth as plain float (not packed short), so scale_factor=1./
    add_offset=0. is the true identity transform here -- we set them
    explicitly anyway rather than lean on that default-if-missing behavior.

    Because this writes exactly one point, ww3_bounc's own fallback (see
    W3BOUNC: when only one file is listed in spec.list, NBO2==1 and its
    interpolation block is skipped entirely) applies this single spectrum
    uniformly to *every* active boundary point on the grid -- lat/lon here
    don't need to sit exactly on a boundary cell for that reason; they're
    mostly informational until you add more points.

    Time is written as plain seconds-since-epoch floats, NOT as a
    datetime64 coordinate. This was found the hard way: when time is
    datetime64, xarray's own CF encoder recomputes the "units" string at
    write time and ignores whatever we set in .encoding["units"] -- for a
    timestamp that lands exactly on midnight it collapses to a bare
    "seconds since 1990-01-01" with no "hh:mm:ss" at all. W3TIMEMD's U2D
    parses that units string by *fixed column position* (verified by
    reading the source), so a truncated string means it reads past the
    real attribute text into whatever's in the underlying buffer -- not
    reliably a crash, just undefined. Keeping time as plain floats (not
    datetime64) means xarray never touches the units/calendar attributes
    we set, so the string we write is exactly the string in the file.

    Parameters
    ----------
    file_path : str
        Output netCDF path.
    lat, lon : float
        Nominal point location, degrees.
    freq : array-like, shape (NK,)
        Frequency bins, Hz. Doesn't have to match the grid's own NK/FR1/XFR --
        ww3_bounc auto-remaps (the SPCONV/W3CSPC path) onto the grid's own
        discretization if these differ, so mismatching is not fatal.
    direction : array-like, shape (NTH,)
        Direction bins, degrees, "coming from" convention (clockwise from
        true north) -- ww3_bounc converts this internally
        (THETA = mod(2.5*pi - deg2rad(direction), 2*pi)).
    efth : array-like, shape (NT, NK, NTH)
        2D variance density spectrum per timestep, m^2 s / rad.
    time : array-like of np.datetime64, optional
        Timestamps for each efth slice. Defaults to a single arbitrary step.
        Converted to plain seconds-since-1990-01-01 floats before writing
        (see note above) -- passed in as datetime64 just for a nicer API.
    """
    freq = np.asarray(freq, dtype=np.float32)
    direction = np.asarray(direction, dtype=np.float32)
    efth = np.asarray(efth, dtype=np.float32)
    if time is None:
        time = np.array(["2020-01-01T00:00:00"], dtype="datetime64[ns]")
    else:
        time = np.asarray(time, dtype="datetime64[ns]")

    time_units = "seconds since 1990-01-01 00:00:00.0"
    epoch = np.datetime64("1990-01-01T00:00:00", "ns")
    time_seconds = (time - epoch) / np.timedelta64(
        1, "s"
    )  # plain float64, not datetime64

    ds = xr.Dataset(
        data_vars={
            "efth": (
                ("time", "frequency", "direction", "latitude", "longitude"),
                efth.reshape(len(time), len(freq), len(direction), 1, 1),
                {
                    "units": "m2 s rad-1",
                    "_FillValue": np.float32(-999.9),  # required: see docstring
                    "scale_factor": np.float32(1.0),  # identity: efth is plain float
                    "add_offset": np.float32(0.0),
                },
            ),
        },
        coords={
            # units/calendar as plain attrs on a plain float array -- see
            # docstring note on why this isn't a datetime64 coordinate.
            "time": (
                "time",
                time_seconds,
                {"units": time_units, "calendar": "standard"},
            ),
            "frequency": ("frequency", freq, {"units": "s-1"}),
            "direction": ("direction", direction, {"units": "degree"}),
            "latitude": ("latitude", np.array([lat], dtype=np.float32)),
            "longitude": ("longitude", np.array([lon], dtype=np.float32)),
        },
    )

    # xarray defaults to adding a _FillValue to every float variable/coord
    # unless told not to; ww3_bounc never reads _FillValue on anything but
    # efth, but there's no reason to write attributes we didn't ask for.
    no_fill = {"_FillValue": None}
    for coord in ("time", "frequency", "direction", "latitude", "longitude"):
        ds[coord].encoding.update(no_fill)

    ds.to_netcdf(file_path, mode="w", format="NETCDF4")
    return ds


def write_ww3_bounc_nml(
    file_dir, spec_list_filename="spec.list", mode="WRITE", interp=2, verbose=1
):
    """
    Write ww3_bounc.nml, the BOUND_NML namelist that drives the ww3_bounc
    preprocessor. Points BOUND%FILE at spec_list_filename (see write_spec_list).

    Parameters
    ----------
    file_dir: str
        Directory to write ww3_bounc.nml to.
    spec_list_filename: str
        Name of the spec-list file BOUND%FILE should point at.
    mode: str
        'WRITE' to build nest.ww3 from spectra files, 'READ' to diagnose an
        existing nest.ww3 instead.
    interp: int
        Interpolation method onto boundary points: 1 (nearest), 2 (linear).
    verbose: int
        Verbosity level: 0, 1, or 2.
    """
    file_dir = Path(file_dir)
    file_dir.mkdir(parents=True, exist_ok=True)

    with open(file_dir / "ww3_bounc.nml", "w") as f:
        f.write(
            "! -------------------------------------------------------------------- !\n"
            "! WAVEWATCH III - ww3_bounc.nml - Boundary input post-processing        !\n"
            "! -------------------------------------------------------------------- !\n"
            "\n"
            "! -------------------------------------------------------------------- !\n"
            "! Define the input boundaries to preprocess via BOUND_NML namelist\n"
            "! Note: When using a rotated pole WW3 grid, the input spectra are\n"
            "! always assumed to be formulated on a standard pole.\n"
            "!\n"
            "! * namelist must be terminated with /\n"
            "! * definitions & defaults:\n"
            "!     BOUND%MODE                 = 'WRITE'            ! ['WRITE'|'READ']\n"
            "!     BOUND%INTERP               = 2                  ! interpolation [1(nearest),2(linear)]\n"
            "!     BOUND%VERBOSE              = 1                  ! [0|1|2]\n"
            "!     BOUND%FILE                 = 'spec.list'        ! input _spec.nc listing file\n"
            "! -------------------------------------------------------------------- !\n"
            "&BOUND_NML\n"
            f"  BOUND%MODE                 = '{mode}'\n"
            f"  BOUND%INTERP               = {interp}\n"
            f"  BOUND%VERBOSE              = {verbose}\n"
            f"  BOUND%FILE                 = '{spec_list_filename}'\n"
            "/\n"
            "\n"
            "! -------------------------------------------------------------------- !\n"
            "! WAVEWATCH III - end of namelist                                      !\n"
            "! -------------------------------------------------------------------- !\n"
        )


def write_spec_list(file_dir, spectra_paths, spec_list_filename="spec.list"):
    """
    Write the spec.list file that ww3_bounc.nml's BOUND%FILE points at: one
    _spec.nc path per line.

    Parameters
    ----------
    file_dir: str
        Directory to write spec_list_filename to.
    spectra_paths: list[str]
        Paths to the per-boundary-point spectra netCDF files.
    spec_list_filename: str
        Name of the file to write.
    """
    file_dir = Path(file_dir)
    file_dir.mkdir(parents=True, exist_ok=True)

    with open(file_dir / spec_list_filename, "w") as f:
        for p in spectra_paths:
            f.write(f"{p}\n")


def jonswap_like_pulse(freq, direction, fp=0.1, dp=250.0, hs_scale=5.0):
    """Rough Gaussian-in-frequency, cos^4-in-direction bump -- not a real
    JONSWAP spectrum, just something with an obvious peak to look at."""
    freq_shape = np.exp(-((freq - fp) ** 2) / (2 * (0.01**2)))
    dtheta = np.deg2rad(((direction - dp + 180) % 360) - 180)
    dir_shape = np.clip(np.cos(dtheta / 2), 0, None) ** 4
    return hs_scale * np.outer(freq_shape, dir_shape)  # (NK, NTH)


def calm_spectrum(freq, direction, floor=1e-4):
    """Small flat baseline -- not exactly 0 (physically implausible) or
    exactly the _FillValue, just a near-nothing sea state."""
    return floor * np.ones((len(freq), len(direction)))


def _boundary_points(ocn_grid, boundaries):
    """One (lat, lon) point per requested boundary side, at that edge's midpoint."""
    ny, nx = ocn_grid.ny, ocn_grid.nx
    edge_index = {
        "south": (0, nx // 2),
        "north": (ny - 1, nx // 2),
        "west": (ny // 2, 0),
        "east": (ny // 2, nx - 1),
    }
    lats = [float(ocn_grid.tlat[edge_index[side]]) for side in boundaries]
    lons = [float(ocn_grid.tlon[edge_index[side]]) for side in boundaries]
    return lats, lons


def process_ww3_obc(
    ocn_grid,
    inputdir,
    boundaries,
    date_range,
    ww3_obc_product_name=None,
    ww3_obc_function_name=None,
):
    """
    Generate WW3 boundary spectra, spec.list, and ww3_bounc.nml into
    <inputdir>/ocnice.

    ww3_obc_product_name/ww3_obc_function_name mirror Case.configure_forcings's
    product_name/function_name pattern for the main IC/OBC product, but are
    unused for now -- they're plumbing for when WW3 OBC sourcing (e.g. ERA5 2D
    wave spectra, or a parent CESM/WW3 run's own point output) is wired through
    raw_data_access. Spectra are generated with a synthetic pulse-then-calm
    generator instead: one boundary point per requested side, each station
    getting its own distinct, identifiable pulse height (station i gets
    hs_scale=2*(i+1)) so that which station's data lands on which grid
    boundary cell can be checked directly against the model's output.

    ww3_bounc.nml is written with INTERP=1 (nearest point, no interpolation)
    rather than the usual linear blend between stations, so that mapping
    stays exact and traceable per the above.

    The time axis must span the full run: WW3 interpolates linearly in time
    between whatever records exist in nest.ww3, but a time axis that runs out
    mid-run permanently disables boundary forcing (an EOF in w3iobcmd.F90
    sets FLBPI=.FALSE. for the rest of the run). Building it hourly across
    [date_range[0], date_range[1]] guarantees coverage regardless of spacing.
    """
    output_dir = Path(inputdir) / "ocnice"
    output_dir.mkdir(parents=True, exist_ok=True)

    lats, lons = _boundary_points(ocn_grid, boundaries)

    # NK/NTH/freq/direction don't need to match the grid's own ww3_grid.inp
    # discretization -- ww3_bounc remaps automatically if they differ.
    NK, NTH = 25, 24
    freq = 0.04118 * 1.1 ** np.arange(NK)
    direction = np.linspace(0, 360, NTH, endpoint=False)

    start, end = (np.datetime64(d) for d in date_range)
    time = np.arange(start, end + np.timedelta64(1, "h"), np.timedelta64(1, "h"))

    pulse_hours = 6

    spectra_names = []
    for i, (lat, lon) in enumerate(zip(lats, lons)):
        # station-distinct amplitude, both during the pulse and after it
        # drops to the calm floor, so each station stays identifiable.
        station_pulse = jonswap_like_pulse(freq, direction, hs_scale=2.0 * (i + 1))
        station_calm = calm_spectrum(freq, direction, floor=1e-4 * (i + 1))
        efth = np.stack(
            [
                station_pulse if t < pulse_hours else station_calm
                for t in range(len(time))
            ]
        )
        name = f"ww3.point{i + 1}_spec.nc"
        write_ww3_boundary_spectrum(
            output_dir / name, lat, lon, freq, direction, efth, time=time
        )
        spectra_names.append(name)

    write_spec_list(output_dir, spectra_names)
    write_ww3_bounc_nml(output_dir, interp=1)
