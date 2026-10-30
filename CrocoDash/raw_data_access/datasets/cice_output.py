"""
Data Access Module -> CICE restart

A global CICE restart carries no time or lat/lon coordinates of its own --
just raw ni/nj/ncat state arrays on the model's native tripole grid index
space. This module index-subsets a restart to a regional domain's bounding
box using the companion CICE grid file (tlon/tlat, in degrees or radians as
their units say) to locate the matching (nj, ni) window, so the result
can be used as a cold-start initial condition for a regional CICE case. The
same window's tlon/tlat/ulon/ulat are attached to the output (in degrees) so
downstream regridding has real coordinates without re-opening the grid file.
"""

from pathlib import Path

import numpy as np
import xarray as xr

from CrocoDash.raw_data_access.base import *


def _degrees(var):
    """var's values in degrees: its units attribute says whether they are
    radians (an older CICE grid file) or degrees (a MOM6 grid file)."""
    if var.attrs.get("units", "").startswith("radian"):
        return np.rad2deg(var.values)
    return var.values


def _grid_window(grid_path, region):
    """The T and U points (tlon, tlat, ulon, ulat, in degrees) of the CICE
    grid at grid_path over region, cut by Region.select, on dims (nj, ni),
    with each point's own row and column in the grid as j and i.

    CICE's U points are each T cell's NE corner. A CICE grid file holds them
    as ulon/ulat, on the T points' shape. A MOM6 grid file's ulon/ulat are
    its C-grid u-points instead, and the corners are qlon/qlat, one row and
    one column bigger, so T cell (j, i)'s corner is qlon[j+1, i+1].
    """
    with xr.open_dataset(grid_path) as grid:
        corners = "u" if grid["ulon"].shape == grid["tlon"].shape else "q"
        points = {
            "tlon": grid["tlon"],
            "tlat": grid["tlat"],
            "ulon": grid[f"{corners}lon"],
            "ulat": grid[f"{corners}lat"],
        }
        ny, nx = grid["tlon"].shape
        # The last ny rows and nx columns: all of an array on the T points'
        # shape, and each T cell's NE corner of a corner grid.
        ds = xr.Dataset(
            {
                name: (("nj", "ni"), _degrees(var)[-ny:, -nx:])
                for name, var in points.items()
            }
        )
    ds["j"], ds["i"] = ("nj", np.arange(ny)), ("ni", np.arange(nx))
    window = region.select(ds, lon="tlon", lat="tlat")
    # Each U point on the longitude branch select put its T point on.
    window["ulon"] = window.tlon + (window.ulon - window.tlon + 180) % 360 - 180
    return window


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
    #
    # `calendar` can't be None the way the other two can: ForcingProduct
    # asserts it is a real Calendar. GREGORIAN is the arbitrary-but-harmless
    # choice -- nothing reads a CICE product's calendar (the CESM CALENDAR xml
    # comes from the MOM6 forcing product in Case.configure_forcings, and
    # calendar.mom6 is only read by the MOM6 OBC regrid), and there's no time
    # axis here to stamp it onto. Revisit when a real dated CICE forcing
    # product lands.
    time_var_name = None
    time_units = None
    calendar = GREGORIAN
    time_sampling = None  # static snapshot; dates are ignored
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
            "time axis of its own, and it is written out as-is, with no "
            "`time` axis added and `dates` ignored. `variables` defaults "
            "to keeping every variable in the restart, since which state "
            "variables exist depends on compile-time CICE options (tracer/"
            "layer counts) that this function has no way to know in advance."
        ),
        type="python",
        buf=2.5,
    )
    def get_cice_restart_subset(
        dates: list,
        region,
        name=None,
        output_folder=Path(""),
        output_filename="cice_restart_subset.nc",
        variables=None,
        restart_path="please_provide_a_path",
        grid_path="please_provide_a_path",
        preview=False,
    ):
        for label, p in (("restart_path", restart_path), ("grid_path", grid_path)):
            if p is None or not Path(p).exists():
                raise FileNotFoundError(f"Provided {label} {p} does not exist.")

        window = _grid_window(grid_path, region)

        with xr.open_dataset(restart_path, decode_times=False) as restart:
            subset = restart.isel(nj=window["j"].values, ni=window["i"].values).load()
        if variables:
            keep = [v for v in variables if v in subset.data_vars]
            missing = [v for v in variables if v not in subset.data_vars]
            if missing:
                CICE_RESTART.logger.warning(
                    f"Requested variables not found in restart {restart_path}: {missing}"
                )
            subset = subset[keep]

        # The restart itself carries no lat/lon -- attach the same window's
        # T-point (tlon/tlat) and U-point (ulon/ulat) coordinates, so
        # downstream regridding (see forcing/cice.py's _regrid_cice_full_grid)
        # has real coordinates to interpolate from without re-opening the grid
        # file itself. Always attached, regardless of the `variables` filter
        # above.
        for coord_name in ("tlon", "tlat", "ulon", "ulat"):
            subset[coord_name] = (("nj", "ni"), window[coord_name].values)

        # Not a real forcing product -- there's no actual time evolution to
        # source, and a CICE restart/initial-condition file is a single
        # static snapshot with no `time` dimension of its own anyway, so the
        # subset is written as-is regardless of the requested date range.
        CICE_RESTART.logger.warning(
            f"cice_restart has no real time evolution -- the single restart "
            f"snapshot ({restart_path}) is being used unchanged for the "
            f"requested range ({dates[0]} to {dates[-1]}). This is a "
            f"stand-in until a real dated CICE forcing product is available."
        )

        if preview:
            return subset

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / output_filename
        subset.load().to_netcdf(output_path)
        return [output_path]
