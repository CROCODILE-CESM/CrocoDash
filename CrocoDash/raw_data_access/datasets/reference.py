"""
Data Access Module -> Reference (fast, deterministic synthetic forcing)

REFERENCE_OCEAN (MOM6) generates plausible-looking forcing data purely in
memory via numpy, with no network access, credentials, or campaign-storage
dependency. Each access method is a pure function of its own (dates,
lat/lon bbox) arguments: same inputs always produce the same output, so
this is safe to use in tests (real assertions, not just "did it not crash")
and in demo notebooks that should look identical on every run.

This is not meant to be physically accurate -- just close enough in shape
(a warm-at-equator thermocline) that the real MOM6 regrid pipeline has
something sensible to chew on, fast.
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
    # The synthetic fields are generated on a daily axis by default.
    native_frequency = "D"
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
        freq=None,
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
        # Synthetic data, so any cadence is free -- honour the request directly.
        time = pd.date_range(
            dates[0], dates[-1], freq=resolve_frequency(REFERENCE_OCEAN, freq)
        )
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
