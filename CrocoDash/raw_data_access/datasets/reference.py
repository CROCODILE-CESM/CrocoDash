"""
Data Access Module -> Reference (fast, deterministic synthetic forcing)

Three products -- REFERENCE_OCEAN (MOM6), REFERENCE_ICE (CICE),
REFERENCE_WAVES (WW3) -- that
generate plausible-looking forcing data purely in memory via numpy, with no
network access, credentials, or campaign-storage dependency. Each access
method is a pure function of its own (dates, lat/lon bbox) arguments: same
inputs always produce the same output, so these are safe to use in tests
(real assertions, not just "did it not crash") and in demo notebooks that
should look identical on every run.

These are not meant to be physically accurate -- just close enough in shape
(a warm-at-equator thermocline, an ice edge that tapers with latitude,
a JONSWAP-shaped wave spectrum) that the real MOM6/CICE/WW3 regrid
pipelines have something sensible to chew on, fast.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.raw_data_access.base import *


class REFERENCE_OCEAN(MOM6ForcingProduct):
    product_name = "reference_ocean"
    description = (
        "Fast, deterministic synthetic ocean IC/OBC data (temperature, "
        "salinity, SSH, currents) for testing and demos -- no network or "
        "campaign-storage access required."
    )
    link = "n/a"
    time_var_name = "time"
    time_units = "days"
    calendar = GREGORIAN
    time_sampling = TimeSampling("D", "mean", "start")
    boundary_fill_method = "regional_mom6"
    tracer_x_coord = "longitude"
    tracer_y_coord = "latitude"
    tracer_lon_coord = "longitude"
    tracer_lat_coord = "latitude"
    u_x_coord = "longitude"
    u_y_coord = "latitude"
    u_lon_coord = "longitude"
    u_lat_coord = "latitude"
    v_x_coord = "longitude"
    v_y_coord = "latitude"
    v_lon_coord = "longitude"
    v_lat_coord = "latitude"
    u_var_name = "u"
    v_var_name = "v"
    eta_var_name = "ssh"
    depth_coord = "depth"
    tracer_var_names = {"temp": "temp", "salt": "salt"}
    # Same MARBL tracer set as CESM_POP_OUTPUT (raw_data_access/datasets/cesm_ocean_output.py)
    # -- identity-mapped since get_reference_ocean_data names its synthetic variables after
    # these keys directly. Lets a MARBL-enabled compset (%MARBL-BIO) use REFERENCE_OCEAN for
    # IC/OBC, e.g. in fast no-network tests, instead of hard-failing in write_metadata().
    marbl_var_names = {
        "PO4": "PO4",
        "NO3": "NO3",
        "SiO3": "SiO3",
        "NH4": "NH4",
        "Fe": "Fe",
        "Lig": "Lig",
        "O2": "O2",
        "DIC": "DIC",
        "DIC_ALT_CO2": "DIC_ALT_CO2",
        "ALK": "ALK",
        "ALK_ALT_CO2": "ALK_ALT_CO2",
        "DOC": "DOC",
        "DON": "DON",
        "DOP": "DOP",
        "DOPr": "DOPr",
        "DONr": "DONr",
        "DOCr": "DOCr",
        "microzooC": "microzooC",
        "mesozooC": "mesozooC",
        "spChl": "spChl",
        "spC": "spC",
        "spP": "spP",
        "spFe": "spFe",
        "diatChl": "diatChl",
        "diatC": "diatC",
        "diatP": "diatP",
        "diatFe": "diatFe",
        "diatSi": "diatSi",
        "diazChl": "diazChl",
        "diazC": "diazC",
        "diazP": "diazP",
        "diazFe": "diazFe",
        "coccoChl": "coccoChl",
        "coccoC": "coccoC",
        "coccoP": "coccoP",
        "coccoFe": "coccoFe",
        "coccoCaCO3": "coccoCaCO3",
    }

    @accessmethod(
        freq_handling="subsample",
        description=(
            "Generates a synthetic ocean dataset over the requested bbox/dates: "
            "temperature warm at the equator and decaying exponentially with "
            "depth, near-constant salinity, a smooth sinusoidal sea-surface "
            "height, and small sinusoidal currents. One value per day."
        ),
        type="python",
    )
    def get_reference_ocean_data(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="reference_ocean.nc",
        variables=None,
        resolution_deg=0.5,
        freq=None,
    ):
        # Coarse by default to keep the downstream ESMF regrid cheap -- pass a
        # smaller resolution_deg for a finer (more expensive) source grid.
        #
        # A MOM6 boundary's bbox is a degenerate line (lon_min == lon_max for
        # an east/west boundary, or lat_min == lat_max for north/south) --
        # pad by 1 degree on every side (same convention GLORYS's own access
        # methods use) so there's always a real 2D grid to regrid from.
        freq = resolve_time_sampling(
            REFERENCE_OCEAN, "get_reference_ocean_data", freq
        ).frequency
        lon = np.arange(lon_min - 1.0, lon_max + 1.0 + resolution_deg, resolution_deg)
        lat = np.arange(lat_min - 1.0, lat_max + 1.0 + resolution_deg, resolution_deg)
        # Layer centers, like GLORYS's depth axis: regional_mom6 rebuilds layer
        # thicknesses from the centers, so the axis must not start at the surface.
        # These are the midpoints of the interfaces below.
        interfaces = np.array(
            [0, 10, 25, 50, 100, 200, 500, 1000, 2000, 4000, 6000], dtype=float
        )
        depth = 0.5 * (interfaces[:-1] + interfaces[1:])
        time = sample_dates(dates[0], dates[-1], freq)
        shape_4d = (len(time), len(depth), len(lat), len(lon))

        # Warm at the equator, decaying exponentially from the surface to an
        # abyssal floor of ~2C -- a rough stand-in for a real thermocline.
        temp = np.broadcast_to(
            28.0
            * np.cos(np.deg2rad(lat))[None, None, :, None]
            * np.exp(-depth[None, :, None, None] / 500.0)
            + 2.0,
            shape_4d,
        )
        # Near-constant with a small smooth latitudinal variation.
        salt = np.broadcast_to(
            34.7 + 0.3 * np.sin(np.deg2rad(lat))[None, None, :, None], shape_4d
        )
        # Smooth basin-scale sinusoidal pattern, standing in for mesoscale SSH.
        ssh = np.broadcast_to(
            0.1
            * np.sin(np.deg2rad(lon))[None, None, :]
            * np.cos(np.deg2rad(lat))[None, :, None],
            (len(time), len(lat), len(lon)),
        )
        # Small sinusoidal currents (not dynamically tied to ssh -- deterministic
        # placeholders, not a physically consistent geostrophic flow).
        u = np.broadcast_to(
            0.05 * np.sin(np.deg2rad(lat))[None, None, :, None], shape_4d
        )
        v = np.broadcast_to(
            0.05 * np.cos(np.deg2rad(lon))[None, None, None, :], shape_4d
        )

        data_vars = {
            "temp": (("time", "depth", "latitude", "longitude"), temp),
            "salt": (("time", "depth", "latitude", "longitude"), salt),
            "u": (("time", "depth", "latitude", "longitude"), u),
            "v": (("time", "depth", "latitude", "longitude"), v),
            "ssh": (("time", "latitude", "longitude"), ssh),
        }
        # One placeholder variable per MARBL tracer, on the same grid as temp/salt --
        # not physically meaningful, just a small positive constant (MARBL's chemistry
        # doesn't tolerate exact zero concentrations) so a %MARBL-BIO compset has real
        # IC/OBC tracer data to regrid instead of failing in write_metadata().
        for tracer in REFERENCE_OCEAN.marbl_var_names:
            data_vars[tracer] = (
                ("time", "depth", "latitude", "longitude"),
                np.full(shape_4d, 1e-6),
            )

        ds = xr.Dataset(
            data_vars,
            coords={
                "time": time,
                "depth": depth,
                "latitude": lat,
                "longitude": lon,
            },
        )
        if variables:
            ds = ds[[v for v in variables if v in ds.data_vars]]

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        ds.to_netcdf(output_path)
        return output_path


# One ice-covered column (all five thickness categories present) sampled from
# a CESM3 CICE restart (b.e30_alpha09b.B1850C_MTso.ne30_t233_wgx3.360, year
# 201, Arctic), rounded. REFERENCE_ICE spreads this column's per-category
# state over its synthetic ice edge so CICE gets a self-consistent restart:
# thermodynamic tracers (enthalpy, salinity, surface temperature) that agree
# with each other, rather than made-up numbers CICE's thermodynamics rejects.
NCAT = 5
NILYR = 8  # ice layers (sice/qice)
NSLYR = 3  # snow layers (qsno, and smice/smliq/rhos/rsnw)
NFSD = 12  # floe size categories (fsd)
N_AERO = 3  # aerosol species
# Share of the column's ice area in each category, and each category's ice
# and snow thickness [m] (vicen/aicen, vsnon/aicen).
_REF_ICE_CATEGORY_FRACTION = [0.4118, 0.1441, 0.1505, 0.1616, 0.1320]
_REF_ICE_THICKNESS = [0.3193, 0.8529, 1.9265, 3.3811, 7.5573]
_REF_SNOW_THICKNESS = [0.04403, 0.02522, 0.03417, 0.06354, 0.2818]
# Per-category (ncat=5) tracers, as CICE stores them in a restart.
_REF_ICE_TRACERS = {
    "Tsfcn": [-6.997, -5.966, -7.349, -9.472, -10.38],
    "iage": [7.651e6, 8.324e6, 9.011e6, 9.395e6, 1.020e7],
    "FY": [0.9999, 0.9996, 0.9969, 0.9973, 0.9966],
    "alvl": [0.9306, 0.6954, 0.1250, 0.06163, 0.02815],
    "vlvl": [0.8380, 0.5866, 0.1098, 0.05896, 0.02688],
    "apnd": [0.4981, 0.2974, 0.2597, 0.2549, 0.2770],
    "hpnd": [0.02510, 0.04004, 0.07895, 0.1360, 0.3304],
    "ipnd": [0.4251, 0.1313, 0.02579, 0.03495, 0.009330],
    "dhs": [0.002310, 0.003290, 0.009960, 0.01456, 0.2321],
    "sice001": [1.966, 1.749, 2.415, 3.015, 5.149],
    "sice002": [1.886, 1.842, 2.634, 3.269, 4.722],
    "sice003": [1.723, 1.816, 2.697, 3.297, 4.184],
    "sice004": [1.601, 1.777, 2.597, 3.152, 3.621],
    "sice005": [1.530, 1.720, 2.433, 2.951, 3.078],
    "sice006": [1.500, 1.649, 2.244, 2.672, 2.628],
    "sice007": [1.503, 1.577, 2.076, 2.356, 2.464],
    "sice008": [1.565, 1.711, 2.287, 2.499, 3.589],
    "qice001": [-1.520e8, -1.429e8, -2.035e8, -2.364e8, -2.750e8],
    "qice002": [-1.871e8, -2.066e8, -2.491e8, -2.668e8, -2.880e8],
    "qice003": [-2.245e8, -2.353e8, -2.620e8, -2.755e8, -2.904e8],
    "qice004": [-2.527e8, -2.517e8, -2.697e8, -2.796e8, -2.894e8],
    "qice005": [-2.712e8, -2.643e8, -2.754e8, -2.811e8, -2.870e8],
    "qice006": [-2.823e8, -2.758e8, -2.802e8, -2.814e8, -2.834e8],
    "qice007": [-2.890e8, -2.855e8, -2.846e8, -2.826e8, -2.761e8],
    "qice008": [-2.929e8, -2.906e8, -2.856e8, -2.822e8, -2.591e8],
    "qsno001": [-1.144e8, -1.139e8, -1.148e8, -1.162e8, -1.158e8],
    "qsno002": [-1.130e8, -1.130e8, -1.138e8, -1.149e8, -1.129e8],
    "qsno003": [-1.117e8, -1.121e8, -1.128e8, -1.136e8, -1.118e8],
    # All ice in the smallest floe size category.
    "fsd001": [1.0] * NCAT,
}
# Restart fields that are zero for this synthetic state (no aerosols, no snow
# redistribution, no freezing onset, ...) but that CICE still reads.
_ZERO_CATEGORY_FIELDS = (
    ["ffrac"]
    + [
        f"{v}{k:03d}"
        for k in range(1, NSLYR + 1)
        for v in ("smice", "smliq", "rhos", "rsnw")
    ]
    + [f"fsd{k:03d}" for k in range(2, NFSD + 1)]
    + [
        f"{v}{k:03d}"
        for k in range(1, N_AERO + 1)
        for v in ("aerosnossl", "aerosnoint", "aeroicessl", "aeroiceint")
    ]
)
_ZERO_2D_FIELDS = (
    ["coszen", "scale_factor", "swvdr", "swvdf", "swidr", "swidf"]
    + ["strocnxT", "strocnyT", "frz_onset", "fsnow"]
    + [f"{v}_{k}" for v in ("stressp", "stressm", "stress12") for k in range(1, 5)]
)


class REFERENCE_ICE(CICEForcingProduct):
    product_name = "reference_ice"
    description = (
        "Fast, deterministic synthetic CICE forcing for testing and demos -- "
        "generates its own grid, no real CICE restart/grid file required. "
        "Writes a complete CICE restart (ncat=5, every field CICE reads), "
        "built from one real ice column spread over a synthetic ice edge, so "
        "CICE can start from it."
    )
    link = "n/a"
    # No real time evolution any more than CICE_RESTART has (see
    # cice_output.py) -- these only exist to satisfy ForcingProduct's
    # generic contract, and `calendar` is the arbitrary-but-harmless
    # GREGORIAN for the same reason given there.
    time_var_name = None
    time_units = None
    calendar = GREGORIAN
    time_sampling = None  # static snapshot; dates are ignored
    u_x_coord = "ni"
    u_y_coord = "nj"
    v_x_coord = "ni"
    v_y_coord = "nj"
    tracer_x_coord = "ni"
    tracer_y_coord = "nj"
    u_var_name = "uvel"
    v_var_name = "vvel"
    tracer_var_names = {}
    depth_coord = None

    @accessmethod(
        description=(
            "Generates a synthetic CICE restart over the requested bbox/dates: "
            "its own regular tlon/tlat/ulon/ulat mesh (no real CICE grid file "
            "needed), total ice concentration tapering linearly from the "
            "bbox's poleward edge to zero at its equatorward edge, split over "
            "five thickness categories with a real ice column's thicknesses "
            "and thermodynamic state, and a small drift velocity."
        ),
        type="python",
    )
    def get_reference_ice_data(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="reference_ice.nc",
        variables=None,
        resolution_deg=0.5,
        freq=None,
    ):
        # Coarse by default to keep the downstream ESMF regrid cheap -- pass a
        # smaller resolution_deg for a finer (more expensive) source grid.
        resolve_time_sampling(REFERENCE_ICE, "get_reference_ice_data", freq)
        lon = np.arange(lon_min, lon_max + resolution_deg, resolution_deg)
        lat = np.arange(lat_min, lat_max + resolution_deg, resolution_deg)
        tlon, tlat = np.meshgrid(lon, lat)

        # Total concentration: 0 at the bbox's equatorward edge (min |lat|), 1
        # at its poleward edge (max |lat|) -- hemisphere-agnostic via abs(),
        # so this works for either a northern or southern-hemisphere bbox.
        edge = (np.abs(tlat) - np.abs(tlat).min()) / (
            np.abs(tlat).max() - np.abs(tlat).min() + 1e-9
        )
        iced = edge > 0

        def per_category(values):
            return np.asarray(values)[:, None, None] * np.ones_like(edge)

        aicen = per_category(_REF_ICE_CATEGORY_FRACTION) * edge
        data = {
            "aicen": aicen,
            "vicen": aicen * per_category(_REF_ICE_THICKNESS),
            "vsnon": aicen * per_category(_REF_SNOW_THICKNESS),
        }
        # Tracers are per unit ice/snow, so they take the column's values
        # wherever there is ice and are zero in open water, as in a real
        # restart.
        for var, values in _REF_ICE_TRACERS.items():
            data[var] = np.where(iced, per_category(values), 0.0)
        for var in _ZERO_CATEGORY_FIELDS:
            data[var] = np.zeros_like(aicen)

        ds = xr.Dataset({var: (("ncat", "nj", "ni"), v) for var, v in data.items()})
        ds["uvel"] = (("nj", "ni"), np.where(iced, 0.02, 0.0))
        ds["vvel"] = (("nj", "ni"), np.where(iced, 0.02, 0.0))
        ds["iceumask"] = (("nj", "ni"), iced.astype(float))
        for var in _ZERO_2D_FIELDS:
            ds[var] = (("nj", "ni"), np.zeros_like(edge))

        ds["tlon"] = (("nj", "ni"), tlon)
        ds["tlat"] = (("nj", "ni"), tlat)
        # No real staggering here (synthetic mesh, not a real B-grid) -- offset
        # by half a cell as a placeholder U-point location.
        ds["ulon"] = (("nj", "ni"), tlon + resolution_deg / 2)
        ds["ulat"] = (("nj", "ni"), tlat + resolution_deg / 2)

        if variables:
            keep = [v for v in variables if v in ds.data_vars]
            ds = ds[keep + ["tlon", "tlat", "ulon", "ulat"]]

        # No real time evolution to source, and (same convention
        # CICE_RESTART.get_cice_restart_subset uses) a CICE restart/initial-
        # condition file is a single static snapshot with no `time`
        # dimension of its own -- so this doesn't add one.
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        ds.to_netcdf(output_path)
        return [output_path]


class REFERENCE_WAVES(WW3ForcingProduct):
    product_name = "reference_waves"
    description = (
        "Fast, deterministic synthetic WW3 boundary wave spectra (JONSWAP-"
        "shaped frequency spectrum, cosine-2s directional spreading) for "
        "testing and demos -- no CDS/network access required."
    )
    link = "n/a"
    time_var_name = "time"
    time_units = None
    calendar = GREGORIAN
    time_sampling = TimeSampling("6h", "point", "start")
    # The synthetic spectrum below is built around waves "coming from" the
    # west (theta0 = 270), so that is what it declares.
    direction_convention = DIRECTION_COMING_FROM
    # Synthetic: every station is open water, so this never fires.
    land_marker = LAND_ZERO

    @accessmethod(
        description=(
            "Generates a synthetic multi-station 2D wave spectrum (JONSWAP "
            "frequency shape, cosine-2s directional spreading) over the "
            "requested bbox/dates, in the same (time, latitude, longitude, "
            "frequency, direction) shape the real decoded ERA5 product uses."
        ),
        type="python",
    )
    def get_reference_wave_spectra(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="reference_waves.nc",
        variables=None,
        freq=None,
    ):
        # Spread the stations along the long axis of the boundary window.
        resolve_time_sampling(REFERENCE_WAVES, "get_reference_wave_spectra", freq)
        n_stations = 3
        if (lon_max - lon_min) >= (lat_max - lat_min):
            lons = np.linspace(lon_min, lon_max, n_stations)
            lats = np.array([(lat_min + lat_max) / 2])
        else:
            lons = np.array([(lon_min + lon_max) / 2])
            lats = np.linspace(lat_min, lat_max, n_stations)
        # Whole-day inclusive on both ends: date_range(..., freq="6h") alone
        # would stop at the last day's 00:00 and drop its 06/12/18:00 steps,
        # so build every 6-hour step of every whole day in the range instead
        # (same "every hour of every requested day" convention era5.py uses).
        days = pd.date_range(dates[0], dates[-1], freq="D")
        time = pd.date_range(days[0], days[-1] + pd.Timedelta(hours=18), freq="6h")
        freq = np.linspace(0.03, 0.25, 12)
        direction = np.linspace(0.0, 360.0, 16, endpoint=False)

        # Standard JONSWAP spectrum: a 2m/8s swell (Hs=2, Tp=8), Phillips
        # constant alpha=0.0081 and peak-enhancement gamma=3.3 are the
        # textbook defaults.
        g, hs, tp, alpha, gamma = 9.81, 2.0, 8.0, 0.0081, 3.3
        fp = 1.0 / tp
        sigma = np.where(freq <= fp, 0.07, 0.09)
        jonswap = (
            alpha
            * g**2
            * (2 * np.pi) ** -4
            * freq**-5
            * np.exp(-1.25 * (fp / freq) ** 4)
            * gamma ** np.exp(-((freq - fp) ** 2) / (2 * sigma**2 * fp**2))
        )

        # Cosine-2s directional spreading around a fixed dominant direction
        # (waves "coming from" the west), normalized to integrate to ~1 over
        # the full circle.
        theta0, s = 270.0, 8
        dtheta = np.deg2rad(direction[1] - direction[0])
        spreading = np.cos(np.deg2rad((direction - theta0) / 2.0)) ** (2 * s)
        spreading = spreading / (spreading.sum() * dtheta)

        base_spectrum = jonswap[:, None] * spreading[None, :]
        efth = np.broadcast_to(
            base_spectrum,
            (len(time), len(lats), len(lons), len(freq), len(direction)),
        ).copy()

        ds = xr.Dataset(
            {
                "wave_spectra": (
                    ("time", "latitude", "longitude", "frequency", "direction"),
                    efth,
                )
            },
            coords={
                "time": time,
                "latitude": lats,
                "longitude": lons,
                "frequency": freq,
                "direction": direction,
            },
        )

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        ds.to_netcdf(output_path)
        return output_path
