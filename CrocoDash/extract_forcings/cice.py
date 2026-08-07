"""CICE forcing for CrocoDash: a single expanded-grid restoring file.

CICE's restoring mechanism (``ice_restoring.F90``) relaxes boundary-adjacent
cells toward a target ice state over time -- the user is separately
extending that Fortran to read the restoring target from an external file
(not visible in this repo yet). This module produces that file: it must
cover the case's regional domain plus a halo (``n_halo_cells`` on every
side, required for the restoring routine), built from a CICE-shaped forcing
product (real global restart, or a fast synthetic stand-in -- see
``product_name``/``function_name`` below) regridded onto every point of
that expanded grid, with the product's own time axis (a single restart
snapshot copied forward, for ``cice_restart``) carried through unchanged.

Unlike MOM6/WW3's OBC, there's no boundary-only regrid and no date-chunking
need (one static snapshot, no real time evolution to fetch incrementally),
so this doesn't route through obc.py's shared GET->chunk->REGRID->MERGE
engine at all -- just resolves the requested product/function via the same
``ProductRegistry`` lookup MOM6/WW3 use (``utils.get_data_access_function``)
instead of hardcoding a single product.

The precise file/variable-naming contract the (not-yet-visible) Fortran
restoring-file reader will expect is unverified -- this produces a file
using CICE's own restart variable names (unchanged, since we're only
windowing+regridding them) over the expanded grid. Revisit once that
Fortran work is available to check against.

Cross-checked against the CICE Consortium's own restoring implementation
(``ice_restoring.F90``, ``ice_restoring_data_restartfiles``): that reader
expects ``aicen``/``vicen``/``vsnon``/``trcrn`` (category-indexed, ncat=5)
on the *same* grid as the regional domain plus the ``restart_ext`` ghost
cells (``nx_global+2``/``ny_global+2`` -- one ring of padding, a fixed
file-format requirement, not a physical restoring-zone choice). We don't
enumerate those variable names -- every variable in the source restart
passes through unfiltered (T-point and U-point alike), a superset of what
that reader currently needs. ``n_halo_cells`` here controls the restoring
zone's physical width, not the ``restart_ext`` padding; it happens to
exceed the 1-cell minimum today, but nothing yet guarantees the outermost
ring is genuine ghost padding rather than real regridded data -- revisit
once the Fortran extension lands. ``uvel``/``vvel`` (B-grid, upper-right
cell corner) are already plumbed through here but not yet consumed by any
reader -- out of scope for the restoring file until the Consortium adds
velocity restoring.
"""

from pathlib import Path

import xarray as xr
from mom6_forge.mapping import regrid_dataset_via_xesmf

from CrocoDash.grid import Grid
from CrocoDash.extract_forcings import utils

# CICE's B-grid stores velocity (uvel/vvel) and its own mask (iceumask) at
# each T-cell's own NW corner -- grid.qlon/qlat, offset by one row/column
# (T-cell (j, i)'s NW corner is qlon[j+1, i]) -- not grid.ulon/ulat (MOM6's
# C-grid u-point, a different physical location). The EVP internal stress
# state (stressp_N/stressm_N/stress12_N -- one field per cell corner) lives
# at that same corner point, not the T-cell center, even though the restart
# stores each numbered field with T-cell (nj, ni) shape -- so these regrid
# through the corner grid too, not the T-point path. Everything else with
# (nj, ni) or (ncat, nj, ni) dims (aicen/vicen/..., coszen, ...) is
# genuinely T-cell-centered, confirmed by inspecting the real restart file.
U_POINT_VARS = {"uvel", "vvel", "iceumask"}
U_POINT_VAR_PREFIXES = ("stressp_", "stressm_", "stress12_")


def _is_u_point_var(name):
    return name in U_POINT_VARS or name.startswith(U_POINT_VAR_PREFIXES)


def _regrid_point_group(ds, vars_, src_lon, src_lat, tgt_lon, tgt_lat):
    if not vars_:
        return xr.Dataset()
    src = ds[vars_].assign_coords(
        lon=(("nj", "ni"), src_lon), lat=(("nj", "ni"), src_lat)
    )
    target = xr.Dataset(
        coords={"lon": (("ny", "nx"), tgt_lon), "lat": (("ny", "nx"), tgt_lat)}
    )
    return regrid_dataset_via_xesmf(src, target, regridding_method="nearest_s2d")


def _regrid_cice_full_grid(ds, grid):
    """ESMF nearest-neighbor regrid of a CICE restart subset (native
    tripole nj/ni index space) onto every T/U point of ``grid``.

    Nearest-neighbor, not bilinear: CICE's category/state fields are
    discrete-like, so sharp ice edges shouldn't be smeared by interpolation.
    """

    t_vars = [
        v
        for v in ds.data_vars
        if v not in ("tlon", "tlat", "ulon", "ulat") and not _is_u_point_var(v)
    ]
    u_vars = [v for v in ds.data_vars if _is_u_point_var(v)]

    t_out = _regrid_point_group(
        ds,
        t_vars,
        ds["tlon"].isel(time=0).values,
        ds["tlat"].isel(time=0).values,
        grid.tlon.values,
        grid.tlat.values,
    )
    u_out = _regrid_point_group(
        ds,
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
    product_name=None,
    function_name=None,
    function_args=None,
    n_halo_cells=2,
):
    """
    Generate CICE's single restoring forcing file into
    <inputdir>/sea_ice/cice_forcing.nc.

    Covers the case's domain plus an ``n_halo_cells``-cell halo on every
    side (grown via ``SupergridBase.expand``), windowed from the requested
    CICE forcing product (``product_name``/``function_name``, resolved via
    the same ``ProductRegistry`` lookup MOM6/WW3 use -- ``restart_path``/
    ``grid_path`` for the real ``cice_restart`` product go in
    ``function_args``) and regridded onto that expanded grid. The output's
    time axis spans ``date_range`` with the product's own snapshot (held
    constant throughout, for ``cice_restart``) carried through.
    """
    hgrid_ds = xr.open_dataset(hgrid_path)
    grid = Grid.from_supergrid_ds(hgrid_ds)
    grid.supergrid = grid.supergrid.expand(n_halo_cells)

    bbox = Grid.get_bounding_boxes(grid)["ic"]

    raw_dir = Path(inputdir) / "extract_forcings" / "cice" / "raw_data"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(inputdir) / "sea_ice"
    output_dir.mkdir(parents=True, exist_ok=True)

    product_name = product_name or "cice_restart"
    function_name = function_name or "get_cice_restart_subset"
    data_access_fn = utils.get_data_access_function(product_name, function_name)
    subset_paths = data_access_fn(
        dates=date_range,
        output_folder=raw_dir,
        **bbox,
        **(function_args or {}),
    )
    subset = xr.open_dataset(subset_paths[0])

    regridded = _regrid_cice_full_grid(subset, grid)
    regridded.to_netcdf(output_dir / "cice_forcing.nc")
