"""
Data Access Module -> Reference (fast, deterministic synthetic forcing)

Two products -- REFERENCE_OCEAN (MOM6), REFERENCE_ICE (CICE) -- that
generate plausible-looking forcing data purely in memory via numpy, with no
network access, credentials, or campaign-storage dependency. Each access
method is a pure function of its own (dates, lat/lon bbox) arguments: same
inputs always produce the same output, so these are safe to use in tests
(real assertions, not just "did it not crash") and in demo notebooks that
should look identical on every run.

These are not meant to be physically accurate -- just close enough in shape
(a warm-at-equator thermocline, an ice edge that tapers with latitude) that
the real MOM6/CICE regrid pipelines have something sensible to chew on,
fast.
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

        ds = xr.Dataset(
            {
                "temp": (("time", "depth", "latitude", "longitude"), temp),
                "salt": (("time", "depth", "latitude", "longitude"), salt),
                "u": (("time", "depth", "latitude", "longitude"), u),
                "v": (("time", "depth", "latitude", "longitude"), v),
                "ssh": (("time", "latitude", "longitude"), ssh),
            },
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


class REFERENCE_ICE(CICEForcingProduct):
    product_name = "reference_ice"
    description = (
        "Fast, deterministic synthetic CICE forcing (ice concentration/"
        "volume/surface temp and a small drift velocity) for testing and "
        "demos -- generates its own grid, no real CICE restart/grid file "
        "required."
    )
    link = "n/a"
    # No real time evolution any more than CICE_RESTART has (see
    # cice_output.py) -- these only exist to satisfy ForcingProduct's
    # generic contract.
    time_var_name = None
    time_units = None
    cf_calendar = None
    cesm_calendar = None
    mom6_calendar = None
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
            "Generates a synthetic single-category CICE-shaped dataset over "
            "the requested bbox/dates: its own regular tlon/tlat/ulon/ulat "
            "mesh (no real CICE grid file needed), ice concentration tapering "
            "linearly from the bbox's poleward edge to zero at its equatorward "
            "edge, matching ice volume/surface temp, and a small drift "
            "velocity."
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
    ):
        # Coarse by default to keep the downstream ESMF regrid cheap -- pass a
        # smaller resolution_deg for a finer (more expensive) source grid.
        lon = np.arange(lon_min, lon_max + resolution_deg, resolution_deg)
        lat = np.arange(lat_min, lat_max + resolution_deg, resolution_deg)
        tlon, tlat = np.meshgrid(lon, lat)

        # 0 at the bbox's equatorward edge (min |lat|), 1 at its poleward edge
        # (max |lat|) -- hemisphere-agnostic via abs(), so this works for
        # either a northern or southern-hemisphere bounding box.
        edge = (np.abs(tlat) - np.abs(tlat).min()) / (
            np.abs(tlat).max() - np.abs(tlat).min() + 1e-9
        )
        aicen = edge[None, :, :]  # single category (ncat=1)
        vicen = 2.0 * aicen
        # -1.8C under thick ice, warming toward the open-water ice edge.
        Tsfcn = -1.8 * aicen - 1.0 * (1.0 - aicen)
        uvel = np.full_like(tlon, 0.02)
        vvel = np.full_like(tlon, 0.02)

        ds = xr.Dataset(
            {
                "aicen": (("ncat", "nj", "ni"), aicen),
                "vicen": (("ncat", "nj", "ni"), vicen),
                "Tsfcn": (("ncat", "nj", "ni"), Tsfcn),
                "uvel": (("nj", "ni"), uvel),
                "vvel": (("nj", "ni"), vvel),
            },
        )
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
