from pathlib import Path

import numpy as np
import xarray as xr

from CrocoDash.extract_forcings import obc
from CrocoDash.grid import Grid


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


# NK/NTH/freq/direction don't need to match the grid's own ww3_grid.inp
# discretization -- ww3_bounc remaps automatically if they differ. Only used
# by _regrid_chunk_placeholder below -- the real ERA5 path uses ERA5's own
# native frequency/direction bins instead (see _extract_all_stations).
_NK, _NTH = 25, 24
_FREQ = 0.04118 * 1.1 ** np.arange(_NK)
_DIRECTION = np.linspace(0, 360, _NTH, endpoint=False)


def _regrid_chunk_placeholder(
    ds, hgrid, boundary, seg_id, outfolder, dataset_varnames, start_date, regridders
):
    """WW3's placeholder regrid step: ignores ds's content except for its
    time axis (however the GET step's stub access function chunked it), and
    writes a simple constant-value spectrum instead, scaled by the boundary's
    point index (seg_id) -- point i = 1e-3*i -- so which station's data lands
    on which grid boundary cell can be checked directly. No file to open (the
    engine hands us the dataset directly) and nothing to regrid.

    Writes a single-station output (station dim of length 1) to outfolder /
    f"forcing_obc_segment_{seg_id:03d}.nc" -- the same station-dimensioned
    shape _regrid_chunk_era5 produces, so process_ww3_obc's finalization
    step works identically for both. No regridder weights to cache, so
    regridders is passed through unchanged.
    """
    time = ds["time"].values

    bbox = Grid.get_bounding_boxes(hgrid)[boundary]
    lat = (bbox["lat_min"] + bbox["lat_max"]) / 2
    lon = (bbox["lon_min"] + bbox["lon_max"]) / 2

    value = 1e-3 * seg_id
    efth = np.full((1, len(time), len(_FREQ), len(_DIRECTION)), value)

    out = xr.Dataset(
        {"efth": (("station", "time", "frequency", "direction"), efth)},
        coords={
            "station": np.arange(1),
            "station_lon": ("station", [lon]),
            "station_lat": ("station", [lat]),
            "time": time,
            "frequency": _FREQ,
            "direction": _DIRECTION,
        },
    )
    out_path = Path(outfolder) / f"forcing_obc_segment_{seg_id:03d}.nc"
    out.to_netcdf(out_path)
    return regridders


def _extract_all_stations(ds):
    """Pull every real spatial point's full (time, frequency, direction)
    spectrum out of a decoded ERA5 wave-spectra window -- no reduction to a
    single point. A boundary's window (see mom6_forge.Grid.get_bounding_boxes)
    is a thin strip running the whole length of that edge, so it typically
    contains several real ERA5 grid points; each becomes its own station,
    left for ww3_bounc's own linear interpolation (see process_ww3_obc) to
    blend between, rather than being collapsed here.

    Grabs ds's one data variable by position rather than a hardcoded name,
    matching whatever `raw_data_access.datasets.era5.decode_era5_spectra_grib`
    (or a test's fake product) named it, as long as the file has exactly one
    data variable (guaranteed for era5.py's real product since the GET step
    only ever requests one param).

    Confirmed against a real ERA5 pull (2026-08-03): the decoded dataset is a
    regular (time, latitude, longitude, frequency, direction) grid -- ERA5's
    native Reduced Lat-Lon wave grid, regridded server-side via the request's
    "grid" key (see era5.py). Every (latitude, longitude) point in the window
    becomes its own station via a stack -- including ones that turn out to be
    all-zero (e.g. land, or genuinely no wave energy at that hour); harmless
    zero-energy stations, not filtered out here.

    Raises a clear error (not a silent misextraction) if `ds` doesn't match
    this shape, since a fake/test product could still get it wrong.

    Returns
    -------
    lons, lats : 1D arrays, one per station
    freq, direction : 1D arrays (assumed shared across all stations -- ERA5's
        wave model uses one fixed global spectral discretization)
    efth : array, shape (n_stations, n_time, n_frequency, n_direction)
    """
    (var_name,) = ds.data_vars
    da = ds[var_name]
    expected = {"time", "latitude", "longitude", "frequency", "direction"}
    missing = expected - set(da.dims)
    if missing:
        raise ValueError(
            f"ERA5 spectrum dataset missing expected dims {missing}; found "
            f"{da.dims}."
        )
    stacked = da.stack(station=("latitude", "longitude"))
    stacked = stacked.transpose("station", "time", "frequency", "direction")
    return (
        stacked["longitude"].values,
        stacked["latitude"].values,
        stacked["frequency"].values,
        stacked["direction"].values,
        stacked.values,
    )


def _regrid_chunk_era5(
    ds, hgrid, boundary, seg_id, outfolder, dataset_varnames, start_date, regridders
):
    """WW3's real regrid step: keeps every real ERA5 point in the fetched
    (buffered) boundary window as its own station, each carrying its own
    unmodified spectrum -- no spatial reduction, no spectral interpolation
    onto WW3's own frequency/direction bins (ww3_bounc's SPCONV/W3CSPC path
    remaps arbitrary bins at read time), no direction-convention or unit
    conversion (ERA5's documented "coming from"/clockwise-from-north
    convention and its m^2 s rad^-1 units already match what
    write_ww3_boundary_spectrum expects -- this rests on ECMWF's documented
    convention, not an independent physical sanity check against a known
    reference spectrum).

    Writes a station-dimensioned output to outfolder /
    f"forcing_obc_segment_{seg_id:03d}.nc", same shape
    _regrid_chunk_placeholder produces. No regridder weights to cache, so
    regridders is passed through unchanged.
    """
    lons, lats, freq, direction, efth = _extract_all_stations(ds)
    time = ds["time"].values

    out = xr.Dataset(
        {"efth": (("station", "time", "frequency", "direction"), efth)},
        coords={
            "station": np.arange(len(lons)),
            "station_lon": ("station", lons),
            "station_lat": ("station", lats),
            "time": time,
            "frequency": freq,
            "direction": direction,
        },
    )
    out_path = Path(outfolder) / f"forcing_obc_segment_{seg_id:03d}.nc"
    out.to_netcdf(out_path)
    return regridders


def process_ww3_obc(
    hgrid_path,
    inputdir,
    boundaries,
    date_range,
    ww3_obc_product_name=None,
    ww3_obc_function_name=None,
    get_step_days=None,
    regrid_step_days=None,
):
    """
    Generate WW3 boundary spectra, spec.list, and ww3_bounc.nml into
    <inputdir>/ocnice.

    get_step_days/regrid_step_days: passed straight through to obc.py's GET/
    REGRID chunking (see mom6.py's process_mom6_obc for the same pattern).
    None (default) fetches/regrids the whole date_range in one request per
    boundary -- fine for the placeholder, but for the real ERA5 product a
    multi-day request expands into a very large number of GRIB messages
    (days * 24 hours * 24 directions * 30 frequencies each) that can take a
    long time to queue/process on CDS. Passing get_step_days=1 splits each
    boundary's GET step into one request per calendar day instead.

    Routes through obc.py's shared GET -> chunk -> REGRID -> MERGE engine.
    ww3_obc_product_name/ww3_obc_function_name default to the placeholder
    WW3 product (see raw_data_access/datasets/ww3.py) -- since the real ERA5
    product (raw_data_access/datasets/era5.py) needs a separate
    cds.climate.copernicus.eu API key not assumed to exist, the default
    isn't flipped to it. Pass ww3_obc_product_name="era5_wave_spectra",
    ww3_obc_function_name="get_era5_2d_spectra" to opt into the real path.
    The regrid step is chosen to match: _regrid_chunk_placeholder for the
    default, _regrid_chunk_era5 for anything else.

    Each boundary's merged output carries a "station" dimension -- one real
    (or, for the placeholder, one synthetic) point per boundary window, not
    reduced to a single value. Finalization below splits every boundary's
    stations out into individual ww3.pointN_spec.nc files (one per real
    station, via write_ww3_boundary_spectrum -- its per-point contract is
    unchanged), and pools ALL boundaries' stations into one global spec.list
    (ww3_bounc's list/interpolation is domain-wide, not scoped to a named
    boundary).

    ww3_bounc.nml's INTERP is chosen to match the same placeholder/real
    split as the regrid step: INTERP=1 (nearest, no interpolation) for the
    placeholder, same as before, since each boundary still only contributes
    one synthetic station and nearest keeps that station's mapping exact and
    traceable; INTERP=2 (linear) for the real ERA5 path, where each boundary
    contributes several real, spatially-distributed stations worth actually
    interpolating between via ww3_bounc's own machinery rather than
    pre-collapsing to one hand-picked point ourselves.

    The time axis must span the full run: WW3 interpolates linearly in time
    between whatever records exist in nest.ww3, but a time axis that runs out
    mid-run permanently disables boundary forcing (an EOF in w3iobcmd.F90
    sets FLBPI=.FALSE. for the rest of the run). The placeholder access
    function builds it hourly across [date_range[0], date_range[1]],
    guaranteeing coverage regardless of spacing.
    """
    output_dir = Path(inputdir) / "ocnice"
    output_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = Path(inputdir) / "extract_forcings" / "ww3"
    raw_dir = staging_dir / "raw_data"
    regridded_dir = staging_dir / "regridded_data"
    merged_dir = staging_dir / "merged"
    for d in (raw_dir, regridded_dir, merged_dir):
        d.mkdir(parents=True, exist_ok=True)

    boundary_number_conversion = {b: i + 1 for i, b in enumerate(boundaries)}
    start_date, end_date = date_range

    product_name = ww3_obc_product_name or "WW3"
    function_name = ww3_obc_function_name or "get_ww3_placeholder_data"
    regrid_chunk_fn = (
        _regrid_chunk_placeholder if product_name == "WW3" else _regrid_chunk_era5
    )

    obc.process_obc_conditions(
        start_date=start_date,
        end_date=end_date,
        boundary_number_conversion=boundary_number_conversion,
        product_name=product_name,
        function_name=function_name,
        variables=[],
        extra_args={},
        dataset_varnames={},
        hgrid_path=hgrid_path,
        raw_dataset_path=raw_dir,
        regridded_dataset_path=regridded_dir,
        output_path=merged_dir,
        regrid_chunk_fn=regrid_chunk_fn,
        get_step_days=get_step_days,
        regrid_step_days=regrid_step_days,
    )

    spectra_names = []
    for boundary in boundaries:
        seg_id = boundary_number_conversion[boundary]
        merged = xr.open_dataset(merged_dir / f"forcing_obc_segment_{seg_id:03d}.nc")
        for k in range(merged.sizes["station"]):
            station = merged.isel(station=k)
            name = f"ww3.point{len(spectra_names) + 1}_spec.nc"
            write_ww3_boundary_spectrum(
                output_dir / name,
                float(station["station_lat"]),
                float(station["station_lon"]),
                station["frequency"].values,
                station["direction"].values,
                station["efth"].values,
                time=station["time"].values,
            )
            spectra_names.append(name)
        merged.close()

    write_spec_list(output_dir, spectra_names)
    interp = 1 if product_name == "WW3" else 2
    write_ww3_bounc_nml(output_dir, interp=interp)
