"""
Data Access Module -> CICE restart

A global CICE restart carries no time or lat/lon coordinates of its own --
just raw ni/nj/ncat state arrays on the model's native tripole grid index
space. This module index-subsets a restart to a regional domain's bounding
box using the companion CICE grid file (tlon/tlat, stored in radians despite
their degrees_* attrs) to locate the matching (nj, ni) window, so the result
can be used as a cold-start initial condition for a regional CICE case. The
same window's tlon/tlat/ulon/ulat are attached to the output (in degrees) so
downstream regridding has real coordinates without re-opening the grid file.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from mom6_forge.utils import longitude_slicer

from CrocoDash.raw_data_access.base import *


def find_cice_index_window(
    grid_path, lat_min, lat_max, lon_min, lon_max, buffer_deg=1.5
):
    """
    Locate the (ni_index, nj_min, nj_max) window on a CICE tripole grid
    (T-point tlon/tlat) covering the given lat/lon bounding box.

    Longitude is resolved via mom6_forge's longitude_slicer against the
    grid's row 0 -- every row of a CICE tripole grid is identical and
    uniformly spaced in longitude below the displaced-pole fold, and row 0
    (the grid's southern edge) is always below it. Latitude doesn't need the
    same periodicity handling (no wraparound), so it's a plain argwhere over
    tlat restricted to the resolved longitude window, which also naturally
    follows the curvature of latitude lines near the fold.

    Known limitation: this returns a contiguous ni index range and can't
    represent a window that straddles the tripole seam itself -- not
    expected for realistic regional domains, since CESM's tripole grids
    place both displaced poles over land specifically to avoid this.
    """
    grid = xr.open_dataset(grid_path)
    tlon = np.rad2deg(grid["tlon"].values)
    tlat = np.rad2deg(grid["tlat"].values)
    ni = tlon.shape[1]

    lon_row = xr.Dataset(
        {"ni_index": ("lon", np.arange(ni))},
        coords={"lon": tlon[0, :]},
    )
    sliced = longitude_slicer(
        lon_row, (lon_min - buffer_deg, lon_max + buffer_deg), "lon"
    )
    ni_idx = sliced["ni_index"].values

    lat_window = tlat[:, ni_idx]
    lat_mask = (lat_window >= lat_min - buffer_deg) & (
        lat_window <= lat_max + buffer_deg
    )
    nj_rows = np.where(lat_mask.any(axis=1))[0]
    if nj_rows.size == 0:
        raise ValueError(
            f"No grid points found in bounding box lat=({lat_min}, {lat_max}) "
            f"lon=({lon_min}, {lon_max}) on grid {grid_path}."
        )
    return ni_idx, int(nj_rows.min()), int(nj_rows.max())


class CICE_RESTART(CICEForcingProduct):
    product_name = "cice_restart"
    description = (
        "Global CICE restart file, index-subset to a regional domain's "
        "bounding box for use as a cold-start initial condition."
    )
    link = "https://escomp.github.io/CICE/versions/master/html/user_guide/ug_case_settings.html"
    # A restart is a single snapshot with no time dimension at all -- these
    # only exist to satisfy ForcingProduct's generic contract and are never
    # read. This product is a temporary stand-in and expected to be replaced
    # by a real CICE forcing product later.
    time_var_name = None
    time_units = None
    cf_calendar = None
    cesm_calendar = None
    # CICE's B-grid stores velocity (uvel/vvel) and tracer-like state on the
    # same (nj, ni) index space -- no separate staggered dims like MOM6's
    # xh/xq. These are real, not placeholders.
    u_x_coord = "ni"
    u_y_coord = "nj"
    v_x_coord = "ni"
    v_y_coord = "nj"
    tracer_x_coord = "ni"
    tracer_y_coord = "nj"
    u_var_name = "uvel"
    v_var_name = "vvel"
    # No 1:1 tracer-name mapping and no depth dimension for a raw restart --
    # its state is category-indexed (aicen/vicen/sice00N/...), not a single
    # named tracer set on depth levels the way ocean tracers are. Unused
    # placeholders, same caveat as the time fields above.
    tracer_var_names = {}
    depth_coord = None

    @accessmethod(
        description=(
            "Reads a global CICE restart file and its companion grid file, "
            "locates the (nj, ni) index window covering the requested lat/lon "
            "bounding box on the grid's T-point coordinates, and writes the "
            "restart subset over that window. Point restart_path at a global "
            "CICE restart (*.cice.r.*.nc) and grid_path at its companion CICE "
            "grid file, e.g. /glade/campaign/cesm/community/omwg/grids/"
            "tx2_3v3_grid.nc for the tx2_3v3 grid. This isn't a real dated "
            "forcing product yet -- a restart is a single snapshot with no "
            "time axis of its own, so the snapshot is just copied forward "
            "onto a daily `time` axis spanning `dates`. `variables` defaults "
            "to keeping every variable in the restart, since which state "
            "variables exist depends on compile-time CICE options (tracer/"
            "layer counts) that this function has no way to know in advance."
        ),
        type="python",
    )
    def get_cice_restart_subset(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="cice_restart_subset.nc",
        variables=None,
        restart_path="please_provide_a_path",
        grid_path="please_provide_a_path",
        buffer_deg=1.5,
        preview=False,
    ):
        for label, p in (("restart_path", restart_path), ("grid_path", grid_path)):
            if p is None or not Path(p).exists():
                raise FileNotFoundError(f"Provided {label} {p} does not exist.")

        ni_idx, nj_min, nj_max = find_cice_index_window(
            grid_path, lat_min, lat_max, lon_min, lon_max, buffer_deg=buffer_deg
        )

        restart = xr.open_dataset(restart_path, decode_times=False)
        subset = restart.isel(nj=slice(nj_min, nj_max + 1), ni=ni_idx)
        if variables:
            keep = [v for v in variables if v in subset.data_vars]
            missing = [v for v in variables if v not in subset.data_vars]
            if missing:
                CICE_RESTART.logger.warning(
                    f"Requested variables not found in restart {restart_path}: {missing}"
                )
            subset = subset[keep]

        # The restart itself carries no lat/lon -- attach the same window's
        # T-point (tlon/tlat) and U-point (ulon/ulat) coordinates from the
        # grid file, converted to degrees, so downstream regridding (see
        # extract_forcings/cice.py's _regrid_cice_chunk) has real coordinates
        # to interpolate from without re-opening the grid file itself. Always
        # attached, regardless of the `variables` filter above.
        grid_ds = xr.open_dataset(grid_path)
        grid_window = grid_ds.isel(nj=slice(nj_min, nj_max + 1), ni=ni_idx)
        for coord_name in ("tlon", "tlat", "ulon", "ulat"):
            subset[coord_name] = (
                ("nj", "ni"),
                np.rad2deg(grid_window[coord_name].values),
            )

        # Not a real forcing product -- there's no actual time evolution to
        # source, so just copy the single snapshot forward onto every day in
        # the requested range.
        time = pd.date_range(dates[0], dates[-1], freq="D")
        subset = subset.expand_dims(time=time)

        if preview:
            return subset

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        subset.load().to_netcdf(output_path)
        return [output_path]
