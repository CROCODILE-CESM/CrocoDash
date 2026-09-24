from pathlib import Path

import numpy as np
import xarray as xr

from CrocoDash.forcing import obc
from CrocoDash.forcing.base import *
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import (
    DIRECTION_COMING_FROM,
    DIRECTION_TO,
    LAND_NAN,
    LAND_ZERO,
    WW3ForcingProduct,
)


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
        Direction bins, degrees, propagating-towards ("to") convention,
        clockwise from true north -- ww3_bounc converts this internally
        (THETA = mod(2.5*pi - deg2rad(direction), 2*pi), ww3_bounc.F90:581),
        which is the exact inverse of what ww3_ounp writes out
        (mod(450 - th_deg, 360), ww3_ounp.F90:3245). Callers hand this axis
        over already converted -- see to_direction_to.
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
                # "gregorian", not the also-CF-valid "standard" -- see
                # raw_data_access/base.py's GREGORIAN calendar constant for why.
                {"units": time_units, "calendar": "gregorian"},
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


def to_direction_to(direction, convention):
    """Rotate a spectrum's direction axis into the "to" convention.

    ``write_ww3_boundary_spectrum`` writes the axis through unchanged, and
    ww3_bounc rebuilds WW3's internal THETA from it as
    ``mod(2.5*pi - deg2rad(direction), 2*pi)`` (ww3_bounc.F90:581) -- the
    exact inverse of what ww3_ounp writes (ww3_ounp.F90:3245). So the number
    in the file has to be the direction the waves are propagating TOWARDS. A
    product that reports "coming from" is the same spectrum rotated 180
    degrees, and only the product knows which it is -- hence
    ``WW3ForcingProduct.direction_convention``.

    Only the axis labels move; ``efth`` is indexed by that axis and is left
    alone. The resulting order can be non-monotonic, which ww3_bounc handles
    (it remaps via W3CSPC whenever THETA(1) != TH(1)).
    """
    if convention == DIRECTION_TO:
        return np.asarray(direction)
    if convention == DIRECTION_COMING_FROM:
        return np.mod(np.asarray(direction) + 180.0, 360.0)
    raise ValueError(
        f"Unknown direction convention {convention!r}; expected "
        f"{DIRECTION_TO!r} or {DIRECTION_COMING_FROM!r}."
    )


# Where process() writes WW3's generated inputs, and therefore where
# get_output_filepaths() looks for them. Kept in one place so the writer, the
# WW3_GRID_INP_DIR setting and the reader cannot drift apart.
WAVE_SUBDIR = "wav"


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


def _remove_boundary_spectra(file_dir):
    """Remove the point spectra, spec.list and ww3_bounc.nml from file_dir."""
    file_dir = Path(file_dir)
    for stale in file_dir.glob("ww3.point*_spec.nc"):
        stale.unlink()
    for name in ("spec.list", "ww3_bounc.nml"):
        (file_dir / name).unlink(missing_ok=True)


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


def _extract_all_stations(ds, land_marker=LAND_ZERO):
    """Pull every real spatial point's full (time, frequency, direction)
    spectrum out of a decoded wave-spectra window -- no reduction to a
    single point. A boundary's window (see mom6_forge.Grid.get_bounding_boxes)
    is a thin strip running the whole length of that edge, so it typically
    contains several real source grid points; each becomes its own station,
    left for ww3_bounc's own linear interpolation (see WW3Configurator.process)
    to blend between, rather than being collapsed here.

    Grabs ds's one data variable by position rather than a hardcoded name,
    matching whatever the product named it (era5.py writes "efth",
    reference.py "wave_spectra"), as long as the file has exactly one data
    variable -- which every WW3ForcingProduct guarantees, a spectrum being
    the only thing any of them emits.

    Confirmed against a real ERA5 pull (2026-08-03): the decoded dataset is a
    regular (time, latitude, longitude, frequency, direction) grid -- ERA5's
    native Reduced Lat-Lon wave grid, regridded server-side via the request's
    "grid" key (see era5.py). cesm_ww3_jra.py's windows are regular by
    construction. Every (latitude, longitude) point in the window becomes its
    own station via a stack. Land stations are dropped, because ww3_bounc
    blends stations by distance and a land station would damp its neighbours.

    How land is recognized depends on the product, which is why
    ``land_marker`` is required metadata. ERA5 has no mask -- its land
    sentinel decodes to 0 -- so for LAND_ZERO products an all-zero station
    is land. That rule cannot be applied blindly: a sea-ice-covered boundary
    carries exactly zero wave energy at every bin, and dropping it would
    leave ww3_bounc extrapolating swell into the ice from open-water
    stations far away, when zero is precisely the right boundary condition.
    So LAND_NAN products (cesm_ww3_jra.py, which has WW3's own mapsta) mark
    land as NaN, and their genuine zeros are kept as real stations.

    Raises a clear error (not a silent misextraction) if `ds` doesn't match
    this shape, since a new or test product could still get it wrong.

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
            f"Wave spectrum dataset missing expected dims {missing}; found "
            f"{da.dims}."
        )
    stacked = da.stack(station=("latitude", "longitude"))
    stacked = stacked.transpose("station", "time", "frequency", "direction")
    spectral_dims = ("time", "frequency", "direction")
    if land_marker == LAND_NAN:
        wet = stacked.notnull().any(dim=spectral_dims).values
        reason = "all-NaN (land)"
    elif land_marker == LAND_ZERO:
        wet = (stacked != 0).any(dim=spectral_dims).values
        reason = "all-zero, which this product uses to mark land"
    else:
        raise ValueError(
            f"Unknown land marker {land_marker!r}; expected "
            f"{LAND_NAN!r} or {LAND_ZERO!r}."
        )
    if not wet.any():
        raise ValueError(f"Every station in the window is {reason}.")
    stacked = stacked.isel(station=wet)
    # A kept station is water, so any residual NaN is a hole in the source
    # rather than land; zero is the only defensible value to hand ww3_bounc,
    # which has no missing-value concept of its own.
    stacked = stacked.fillna(0.0)
    return (
        stacked["longitude"].values,
        stacked["latitude"].values,
        stacked["frequency"].values,
        stacked["direction"].values,
        stacked.values,
    )


def _wrap_lons_like(lons, ref_lons):
    """Put lons on the same longitude branch as ref_lons ([0, 360) or [-180, 180))."""
    lons = np.asarray(lons, dtype=float) % 360.0
    if np.min(ref_lons) < 0.0:
        lons = np.where(lons >= 180.0, lons - 360.0, lons)
    return lons


def _regrid_chunk_spectra(
    ds, hgrid, boundary, seg_id, outfolder, dataset_varnames, start_date, regridders
):
    """WW3's regrid step: keeps every real source point in the fetched
    (buffered) boundary window as its own station, each carrying its own
    unmodified spectrum -- no spatial reduction and no spectral
    interpolation onto WW3's own frequency/direction bins (ww3_bounc's
    SPCONV/W3CSPC path remaps arbitrary bins at read time). Units are passed
    through as well: every WW3ForcingProduct emits m^2 s rad^-1, which is
    what write_ww3_boundary_spectrum expects.

    The direction axis is the one thing that is converted, because it is the
    one thing products disagree about: ``dataset_varnames["direction_
    convention"]`` says which convention this product emits, and the file
    ww3_bounc reads has to be in "to" -- see to_direction_to.
    ``dataset_varnames["land_marker"]`` likewise says how to tell that
    product's land from a becalmed or ice-covered sea point.

    Writes a station-dimensioned output to outfolder /
    f"forcing_obc_segment_{seg_id:03d}.nc". No regridder weights to cache,
    so regridders is passed through unchanged.
    """
    lons, lats, freq, direction, efth = _extract_all_stations(
        ds, land_marker=dataset_varnames["land_marker"]
    )
    if hgrid is not None:
        lons = _wrap_lons_like(lons, hgrid["x"].values)
    direction = to_direction_to(direction, dataset_varnames["direction_convention"])
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


@register
class WW3Configurator(BaseConfigurator):
    name = "WW3"
    process_components = {"ww3": "process"}
    required_for_compsets = ["WW3"]
    allowed_compsets = ["WW3"]
    input_params = [
        InputValueParam("case_inputdir", comment="Case input directory"),
        InputValueParam(
            "boundaries",
            comment="Open boundary sides to generate WW3 spectra for (e.g., ['N', 'S', 'E', 'W'])",
        ),
        InputValueParam(
            "ww3_obc_product_name",
            comment=(
                "WW3 boundary-spectra product, together with "
                "ww3_obc_function_name. One of 'CESM-WW3-JRA' (a JRA-forced "
                "global WW3 run's spectra on GLADE -- no credentials, same "
                "winds as the case's own forcing), 'era5_wave_spectra' (needs "
                "a cds.climate.copernicus.eu API key) or 'reference_waves' "
                "(synthetic, for tests and demos). Required for a WW3 case; "
                "pass 'none' to run without boundary spectra, in which case "
                "the open boundary ring stays calm."
            ),
        ),
        InputValueParam(
            "ww3_obc_function_name",
            comment=(
                "Name of the raw_data_access function to call for downloading the "
                "WW3 OBC data product. Must be given whenever ww3_obc_product_name "
                "is; there is no implicit default. See ww3_obc_product_name."
            ),
        ),
        InputValueParam(
            "ww3_obc_function_overrides",
            comment=(
                "Overrides for ww3_obc_function_name's defaulted arguments, "
                "e.g. {'cdsapi_rc_path': '~/.cdsapirc_cds'}. Defaults (None) to "
                "the function's own defaults."
            ),
        ),
        InputValueParam(
            "get_step_days",
            comment=(
                "Chunk the GET step by this many days per request (e.g. 1 for "
                "one CDS request per day per boundary). Defaults (None) to one "
                "request spanning the whole date_range. Useful for real "
                "products with slow/rate-limited APIs (e.g. ERA5 2D spectra via "
                "CDS): smaller requests turn around faster and let a resumed "
                "run pick up wherever an earlier one left off, since the GET "
                "step skips any per-chunk file that already exists on disk."
            ),
        ),
        InputValueParam(
            "regrid_step_days",
            comment="Chunk the REGRID step by this many days per request. See get_step_days.",
        ),
    ]
    output_params = [
        XMLConfigParam(
            "WW3_GRID_INP_DIR",
            comment="Directory containing WW3 grid input files",
        ),
    ]

    def __init__(
        self,
        case_inputdir,
        boundaries,
        ww3_obc_product_name=None,
        ww3_obc_function_name=None,
        ww3_obc_function_overrides=None,
        get_step_days=None,
        regrid_step_days=None,
    ):
        super().__init__(
            case_inputdir=case_inputdir,
            boundaries=boundaries,
            ww3_obc_product_name=ww3_obc_product_name,
            ww3_obc_function_name=ww3_obc_function_name,
            ww3_obc_function_overrides=ww3_obc_function_overrides,
            get_step_days=get_step_days,
            regrid_step_days=regrid_step_days,
        )

    def validate_args(self, **kwargs):
        super().validate_args(**kwargs)

        boundaries = kwargs["boundaries"]
        if not isinstance(boundaries, list) or not all(
            isinstance(b, str) for b in boundaries
        ):
            raise TypeError("boundaries must be a list of strings.")

        product_name = kwargs["ww3_obc_product_name"]
        function_name = kwargs["ww3_obc_function_name"]
        if product_name is None:
            if function_name is not None:
                raise ValueError(
                    "ww3_obc_function_name was given but ww3_obc_product_name was not."
                )
            raise ValueError(
                "ww3_obc_product_name is required for a WW3 case: name a WW3 forcing "
                "product together with ww3_obc_function_name, or pass 'none' to run "
                "without boundary spectra."
            )
        if product_name == "none":
            if function_name is not None:
                raise ValueError(
                    "ww3_obc_function_name must not be given when "
                    "ww3_obc_product_name is 'none'."
                )
            return
        ProductRegistry.load()
        if not ProductRegistry.product_exists(product_name):
            raise ValueError(
                f"Unknown forcing product '{product_name}'. Known products: "
                f"{sorted(ProductRegistry.products)}."
            )
        if not ProductRegistry.product_is_of_type(product_name, WW3ForcingProduct):
            raise ValueError(
                f"Product '{product_name}' ({ProductRegistry.get_product(product_name).__name__}) "
                "is not a WW3ForcingProduct, so it can't be used as "
                "ww3_obc_product_name (WW3's boundary spectra). If this is a MOM6 "
                "initial/boundary condition product, pass it as product_name instead."
            )
        if function_name is None:
            raise ValueError(
                "ww3_obc_product_name was given but ww3_obc_function_name was not."
            )

    def configure(self):
        self.set_output_param(
            "WW3_GRID_INP_DIR",
            str(Path(self.get_input_param("case_inputdir")) / WAVE_SUBDIR),
        )
        super().configure()

    def get_output_filepaths(self, ocn_ice_directory):
        """Everything WW3 generated, which is a whole directory rather than a
        fixed set of named files.

        The base implementation walks output_params for is_file entries, and
        all of WW3's are XML settings -- WW3_GRID_INP_DIR even holds the
        directory rather than any single file. Without this override the base
        returns nothing, so CaseBundle.bundle() copies no WW3 input at all and
        validate_output_filepaths() passes vacuously.

        Globbing rather than naming files is deliberate: process() writes one
        ww3.pointN_spec.nc per boundary station, so the count is not known up
        front, and spec.list references those paths while ww3_bounc.nml
        references spec.list. The directory is the unit that stays coherent,
        which is also why WW3_GRID_INP_DIR points at it.

        ocn_ice_directory is <inputdir>/ocn; process() writes to
        <inputdir>/wav (WAVE_SUBDIR), hence the sibling lookup.
        """
        wave_dir = Path(ocn_ice_directory).parent / WAVE_SUBDIR
        if not wave_dir.is_dir():
            return []
        return sorted(p for p in wave_dir.iterdir() if p.is_file())

    def process(self, ctx):
        """
        Generate WW3 boundary spectra, spec.list, and ww3_bounc.nml into
        <inputdir>/wav (WAVE_SUBDIR).

        get_step_days/regrid_step_days: passed straight through to obc.py's
        GET/REGRID chunking (see forcing/mom6.py's process_bc for the same
        pattern). None (default) fetches/regrids the whole date range in one
        request per boundary -- for the real ERA5 product, a multi-day
        request expands into a very large number of GRIB messages (days * 24
        hours * 24 directions * 30 frequencies each) that can take a long
        time to queue/process on CDS. Passing get_step_days=1 splits each
        boundary's GET step into one request per calendar day instead.

        ww3_obc_product_name is required: a WW3 forcing product together with
        ww3_obc_function_name, or 'none' to skip boundary spectra (the open
        boundary ring then stays calm).

        Routes through obc.py's shared GET -> chunk ->
        REGRID -> MERGE engine. The product must match a WW3ForcingProduct-
        derived class's spectral contract (enforced in validate_args); e.g.
        'CESM-WW3-JRA' / 'get_cesm_ww3_jra_spectra'
        (raw_data_access/datasets/cesm_ww3_jra.py).

        Each boundary's merged output carries a "station" dimension -- one
        real point per boundary window, not reduced to a single value.
        Finalization below splits every boundary's stations out into
        individual ww3.pointN_spec.nc files (one per real station, via
        write_ww3_boundary_spectrum -- its per-point contract is unchanged),
        and pools ALL boundaries' stations into one global spec.list
        (ww3_bounc's list/interpolation is domain-wide, not scoped to a
        named boundary).

        ww3_bounc.nml's INTERP is set to 2 (linear): each boundary
        contributes several real, spatially-distributed stations worth
        actually interpolating between via ww3_bounc's own machinery,
        rather than pre-collapsing to one hand-picked point ourselves.

        The time axis must span the full run: WW3 interpolates linearly in
        time between whatever records exist in nest.ww3, but a time axis
        that runs out mid-run permanently disables boundary forcing (an EOF
        in w3iobcmd.F90 sets FLBPI=.FALSE. for the rest of the run).
        """
        product_name = self.get_input_param("ww3_obc_product_name")
        function_name = self.get_input_param("ww3_obc_function_name")
        ProductRegistry.load()

        # WW3_GRID_INP_DIR points here whether or not there are boundary
        # spectra in it, so make it real before the opt-out below.
        output_dir = Path(ctx.inputdir) / WAVE_SUBDIR
        output_dir.mkdir(parents=True, exist_ok=True)

        if product_name == "none":
            # A previous run's spectra would otherwise still reach ww3_bounc.
            _remove_boundary_spectra(output_dir)
            print("[info] WW3: ww3_obc_product_name='none' -- no boundary spectra.")
            return

        boundaries = self.get_input_param("boundaries")
        conditions = ctx.config["conditions"]
        start_date = conditions["inputs"]["start_date"]
        end_date = conditions["inputs"]["end_date"]

        staging_dir = Path(ctx.inputdir) / "extract_forcings" / "ww3"
        raw_dir = staging_dir / "raw_data"
        regridded_dir = staging_dir / "regridded_data"
        merged_dir = staging_dir / "merged"
        for d in (raw_dir, regridded_dir, merged_dir):
            d.mkdir(parents=True, exist_ok=True)

        boundary_number_conversion = {b: i + 1 for i, b in enumerate(boundaries)}

        obc.process_obc_conditions(
            start_date=start_date,
            end_date=end_date,
            boundary_number_conversion=boundary_number_conversion,
            product_name=product_name,
            function_name=function_name,
            variables=[],
            extra_args=self.get_input_param("ww3_obc_function_overrides") or {},
            dataset_varnames={
                "direction_convention": ProductRegistry.get_product(
                    product_name
                ).direction_convention,
                "land_marker": ProductRegistry.get_product(product_name).land_marker,
            },
            hgrid_path=ctx.supergrid_path,
            raw_dataset_path=raw_dir,
            regridded_dataset_path=regridded_dir,
            output_path=merged_dir,
            regrid_chunk_fn=_regrid_chunk_spectra,
            get_step_days=self.get_input_param("get_step_days"),
            regrid_step_days=self.get_input_param("regrid_step_days"),
        )

        # This splits the per-boundary file into per-point file (which is
        # what ww3_bounc actually reads) and writes the spec.list and
        # ww3_bounc.nml that point files need to be listed in and read by.
        # Write each station location once; ww3_bounc cannot handle duplicates.
        # The old set is only removed now that the new one has been built, so
        # a failed re-run leaves the previous spectra in place.
        _remove_boundary_spectra(output_dir)
        spectra_names = []
        seen = set()
        for boundary in boundaries:
            seg_id = boundary_number_conversion[boundary]
            merged = xr.open_dataset(
                merged_dir / f"forcing_obc_segment_{seg_id:03d}.nc"
            )
            for k in range(merged.sizes["station"]):
                station = merged.isel(station=k)
                loc = (float(station["station_lat"]), float(station["station_lon"]))
                if loc in seen:
                    continue
                seen.add(loc)
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
        write_ww3_bounc_nml(output_dir, interp=2)
