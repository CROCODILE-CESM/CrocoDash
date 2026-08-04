"""CICE forcing for CrocoDash: a single expanded-grid restoring file.

CICE's restoring mechanism (``ice_restoring.F90``) relaxes boundary-adjacent
cells toward a target ice state over time -- the user is separately
extending that Fortran to read the restoring target from an external file
(not visible in this repo yet). This module produces that file: it must
cover the case's regional domain plus a halo (``n_halo_cells`` on every
side, required for the restoring routine), built from a real global CICE
restart regridded onto every point of that expanded grid, with the single
restart snapshot copied forward across a time axis spanning the whole run
(``CICE_RESTART.get_cice_restart_subset``'s existing behavior, reused as-is).

Unlike MOM6/WW3's OBC, there's no boundary-only regrid and no date-chunking
need (one static snapshot, no real time evolution to fetch incrementally),
so this doesn't route through obc.py's shared GET->chunk->REGRID->MERGE
engine at all.

The precise file/variable-naming contract the (not-yet-visible) Fortran
restoring-file reader will expect is unverified -- this produces a file
using CICE's own restart variable names (unchanged, since we're only
windowing+regridding them) over the expanded grid. Revisit once that
Fortran work is available to check against.
"""

from pathlib import Path

import xarray as xr
from mom6_forge.mapping import regrid_dataset_via_xesmf

from CrocoDash.grid import Grid
from CrocoDash.raw_data_access.datasets.cice_output import CICE_RESTART

# CICE's B-grid stores velocity (uvel/vvel) and its own mask (iceumask) at
# each T-cell's own NW corner -- grid.qlon/qlat, offset by one row/column
# (T-cell (j, i)'s NW corner is qlon[j+1, i]) -- not grid.ulon/ulat (MOM6's
# C-grid u-point, a different physical location). Everything else with
# (nj, ni) or (ncat, nj, ni) dims (aicen/vicen/..., coszen, stressp_N/
# stressm_N/stress12_N, ...) is genuinely T-cell-centered, confirmed by
# inspecting the real restart file.
U_POINT_VARS = {"uvel", "vvel", "iceumask"}


def _regrid_cice_full_grid(ds, grid):
    """ESMF nearest-neighbor regrid of a CICE restart subset (native
    tripole nj/ni index space) onto every T/U point of ``grid``.

    Nearest-neighbor, not bilinear: CICE's category/state fields are
    discrete-like, so sharp ice edges shouldn't be smeared by interpolation.
    """

    def _regrid(vars_, src_lon, src_lat, tgt_lon, tgt_lat):
        if not vars_:
            return xr.Dataset()
        src = ds[vars_].assign_coords(
            lon=(("nj", "ni"), src_lon), lat=(("nj", "ni"), src_lat)
        )
        target = xr.Dataset(
            coords={"lon": (("ny", "nx"), tgt_lon), "lat": (("ny", "nx"), tgt_lat)}
        )
        return regrid_dataset_via_xesmf(src, target, regridding_method="nearest_s2d")

    t_vars = [
        v
        for v in ds.data_vars
        if v not in ("tlon", "tlat", "ulon", "ulat") and v not in U_POINT_VARS
    ]
    u_vars = [v for v in U_POINT_VARS if v in ds.data_vars]

    t_out = _regrid(
        t_vars,
        ds["tlon"].isel(time=0).values,
        ds["tlat"].isel(time=0).values,
        grid.tlon.values,
        grid.tlat.values,
    )
    u_out = _regrid(
        u_vars,
        ds["ulon"].isel(time=0).values,
        ds["ulat"].isel(time=0).values,
        grid.qlon.values[1:, :-1],
        grid.qlat.values[1:, :-1],
    )
    if u_vars:
        u_out = u_out.rename({"lon": "u_lon", "lat": "u_lat"})

    return xr.merge([t_out, u_out])


def process_cice_forcing(
    hgrid_path,
    inputdir,
    date_range,
    restart_path,
    grid_path,
    n_halo_cells=2,
):
    """
    Generate CICE's single restoring forcing file into
    <inputdir>/ocnice/cice_forcing.nc.

    Covers the case's domain plus an ``n_halo_cells``-cell halo on every
    side (grown via ``SupergridBase.expand``), windowed from a real global
    CICE restart (``restart_path``/``grid_path``) and regridded onto that
    expanded grid. The output's time axis spans ``date_range`` with the
    restart's single snapshot held constant throughout.
    """
    hgrid_ds = xr.open_dataset(hgrid_path)
    grid = Grid.from_supergrid_ds(hgrid_ds)
    grid.supergrid = grid.supergrid.expand(n_halo_cells)

    bbox = Grid.get_bounding_boxes(grid)["ic"]

    raw_dir = Path(inputdir) / "extract_forcings" / "cice" / "raw_data"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(inputdir) / "ocnice"
    output_dir.mkdir(parents=True, exist_ok=True)

    subset_paths = CICE_RESTART.get_cice_restart_subset(
        dates=date_range,
        restart_path=restart_path,
        grid_path=grid_path,
        output_folder=raw_dir,
        **bbox,
    )
    subset = xr.open_dataset(subset_paths[0])

    regridded = _regrid_cice_full_grid(subset, grid)
    regridded.to_netcdf(output_dir / "cice_forcing.nc")
