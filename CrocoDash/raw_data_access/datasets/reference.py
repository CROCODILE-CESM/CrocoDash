"""
Data Access Module -> Reference (fast, deterministic synthetic forcing)

Two products -- REFERENCE_OCEAN (MOM6), REFERENCE_WAVES (WW3) -- that
generate plausible-looking forcing data purely in memory via numpy, with no
network access, credentials, or campaign-storage dependency. Each access
method is a pure function of its own (dates, lat/lon bbox) arguments: same
inputs always produce the same output, so these are safe to use in tests
(real assertions, not just "did it not crash") and in demo notebooks that
should look identical on every run.

These are not meant to be physically accurate -- just close enough in shape
(a warm-at-equator thermocline, a JONSWAP-shaped wave spectrum) that the
real MOM6/WW3 regrid pipelines have something sensible to chew on, fast.
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
    ):
        # Coarse by default to keep the downstream ESMF regrid cheap -- pass a
        # smaller resolution_deg for a finer (more expensive) source grid.
        #
        # A MOM6 boundary's bbox is a degenerate line (lon_min == lon_max for
        # an east/west boundary, or lat_min == lat_max for north/south) --
        # pad by 1 degree on every side (same convention GLORYS's own access
        # methods use) so there's always a real 2D grid to regrid from.
        lon = np.arange(lon_min - 1.0, lon_max + 1.0 + resolution_deg, resolution_deg)
        lat = np.arange(lat_min - 1.0, lat_max + 1.0 + resolution_deg, resolution_deg)
        depth = np.array([0, 10, 25, 50, 100, 200, 500, 1000, 2000, 4000], dtype=float)
        time = pd.date_range(dates[0], dates[-1], freq="D")
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
    ):
        n_stations = 3
        lons = np.linspace(lon_min, lon_max, n_stations)
        lats = np.array([(lat_min + lat_max) / 2])
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
