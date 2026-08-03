"""CICE-specific OBC/IC handling for CrocoDash.

Final CICE OBC output files are named ``cice_forcing_obc_segment_NNN.nc`` in
<inputdir>/ocnice -- distinct from MOM6's own ``forcing_obc_segment_NNN.nc``
in the same directory (see ``mom6.py``). Both engines share obc.py's
internal ``forcing_obc_segment_NNN.nc`` convention for chunk files, but each
target writes to its own private staging/merge directory first (mirroring
``ww3.py``) and only copies the final merged file into the shared
``ocnice`` directory under its own distinct name -- otherwise CICE and MOM6
OBC output would silently overwrite each other.

``obc.py``/``ic.py`` are model-agnostic engines (see their module
docstrings): they get raw data (and, for OBC, date-chunk/merge it) but know
nothing about how to regrid it onto a target model's grid. This module
supplies CICE's own default product for the GET step -- the
``raw_data_access`` ``cice_restart`` product (see
``raw_data_access/datasets/cice.py``), the only real ``CICEForcingProduct``
registered so far -- the same role ``mom6.py``'s ``build_forcing_request``
and ``ww3.py``'s ``WW3`` default play for their own targets.

The REGRID step (``_regrid_cice_chunk``) implements a first-pass design built
on explicit, documented assumptions about CICE's B-grid boundary geometry
(see ``_cice_boundary_lines``) rather than verified CICE OBC source -- none
exists on this filesystem; this is unreleased dev work. Revisit those
assumptions once real source/docs are available.
"""

import shutil
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree

from CrocoDash.extract_forcings import obc
from CrocoDash.grid import Grid
from CrocoDash.raw_data_access.registry import ProductRegistry

# CICE stores these on the same (nj, ni) T-cell index array as tracers, but
# they're physically defined at that cell's own designated corner (see
# _cice_boundary_lines) rather than at the cell center. Everything else with
# (nj, ni) or (ncat, nj, ni) dims (aicen/vicen/..., coszen, stressp_N/
# stressm_N/stress12_N, ...) is genuinely T-cell-centered -- including the
# per-corner stress components (stressp_1..4 etc: CICE's EVP dynamics stores
# stress at each T-cell's own 4 corners as 4 separate T-indexed variables,
# confirmed by inspecting the real restart file -- so no separate corner-line
# geometry is needed for stress beyond the T-point line).
U_POINT_VARS = {"uvel", "vvel", "iceumask"}


def _cice_boundary_lines(grid, boundary):
    """Boundary-strip target geometry for one edge of a regional CICE
    domain, built directly from ``grid.tlon``/``tlat`` (T/tracer centers)
    and ``grid.qlon``/``qlat`` (corner points).

    CICE's B-grid designates each T-cell's own NW ("top-left") corner as
    where that cell's velocity (uvel/vvel) lives -- confirmed convention,
    not something regional_mom6.Segment's C-grid staggering can express, so
    this is CICE's own geometry helper, not a reuse of Segment.

    Applying that NW-corner rule to grid.qlon/qlat's indexing (qlon has
    shape (ny+1, nx+1); T-cell (j, i) has NW corner qlon[j+1, i]) is NOT
    symmetric across boundaries:

    - north/west: the boundary-most T-row/column's own U-point (NW corner)
      IS the true domain edge -- e.g. the last T-row's NW corner is
      qlon[-1, :], the outermost corner row; the first T-column's NW corner
      is qlon[:, 0], the outermost corner column.
    - south/east: the boundary-most T-row/column's own U-point is one cell
      *inside* the true edge -- e.g. the first T-row's NW corner is
      qlon[1, :], not the true edge qlon[0, :]; the last T-column's NW
      corner is qlon[:, -2], not the true edge qlon[:, -1].

    This function always returns each boundary's own T-row/column's native
    U-point (an explicit assumption, made in the absence of real CICE OBC
    source/docs -- this is unreleased dev work, confirmed absent from every
    CESM install on this filesystem -- revisit once that's available).

    Returns
    -------
    dict with keys "t_lon"/"t_lat" (tracer-center line) and "u_lon"/"u_lat"
    (velocity corner line) -- 1D arrays, one entry per boundary-most T-cell.
    """
    tlon, tlat = grid.tlon.values, grid.tlat.values
    qlon, qlat = grid.qlon.values, grid.qlat.values

    if boundary == "south":
        t_lon, t_lat = tlon[0, :], tlat[0, :]
        u_lon, u_lat = qlon[1, :-1], qlat[1, :-1]
    elif boundary == "north":
        t_lon, t_lat = tlon[-1, :], tlat[-1, :]
        u_lon, u_lat = qlon[-1, :-1], qlat[-1, :-1]
    elif boundary == "west":
        t_lon, t_lat = tlon[:, 0], tlat[:, 0]
        u_lon, u_lat = qlon[1:, 0], qlat[1:, 0]
    elif boundary == "east":
        t_lon, t_lat = tlon[:, -1], tlat[:, -1]
        u_lon, u_lat = qlon[1:, -2], qlat[1:, -2]
    else:
        raise ValueError(f"Unknown boundary {boundary!r}")

    return {"t_lon": t_lon, "t_lat": t_lat, "u_lon": u_lon, "u_lat": u_lat}


def _nearest_indices(src_lon, src_lat, tgt_lon, tgt_lat):
    """Flat nearest-neighbor (j, i) index into a (nj, ni)-shaped source grid
    for each target point, via a KD-tree on lon/lat.

    Nearest-neighbor rather than bilinear: simplest thing that's well-defined
    everywhere with no extrapolation edge cases, appropriate as a first pass
    given the regridding design itself is an explicit assumption (see
    _cice_boundary_lines) rather than something verified against real CICE
    OBC behavior. No periodic/antimeridian handling needed -- target points
    always fall well within the GET step's already-windowed source subset.
    """
    src_points = np.column_stack([src_lon.ravel(), src_lat.ravel()])
    tree = cKDTree(src_points)
    _, flat_idx = tree.query(np.column_stack([tgt_lon, tgt_lat]))
    j_idx, i_idx = np.unravel_index(flat_idx, src_lon.shape)
    return j_idx, i_idx


def _regrid_cice_chunk(
    ds, hgrid, boundary, seg_id, outfolder, dataset_varnames, start_date, regridders
):
    """CICE's OBC regrid step: nearest-neighbor pick from the windowed
    restart's native (nj, ni) grid onto this boundary's T/U-point lines (see
    _cice_boundary_lines and _nearest_indices for what's assumed vs. settled).

    ``ds`` is whatever the GET step produced -- today,
    ``CICE_RESTART.get_cice_restart_subset``'s output: a single restart
    snapshot copied across a daily time axis, already windowed to the
    boundary's lat/lon bounding box, on the native CICE tripole (nj, ni)
    index space, with tlon/tlat/ulon/ulat (degrees) attached over that same
    window.

    Writes every (nj, ni)/(ncat, nj, ni) variable in ``ds``, reindexed onto
    the boundary's "boundary_point" dimension, to
    outfolder / f"forcing_obc_segment_{seg_id:03d}.nc" -- the filename
    obc.py's generic engine expects to rename per-chunk. No regridder
    weights to cache (nearest-neighbor index lookup is cheap to redo per
    chunk), so regridders is passed through unchanged.
    """
    grid = Grid.from_supergrid_ds(hgrid)
    lines = _cice_boundary_lines(grid, boundary)

    tlon_src = ds["tlon"].isel(time=0).values
    tlat_src = ds["tlat"].isel(time=0).values
    ulon_src = ds["ulon"].isel(time=0).values
    ulat_src = ds["ulat"].isel(time=0).values

    t_j, t_i = _nearest_indices(tlon_src, tlat_src, lines["t_lon"], lines["t_lat"])
    u_j, u_i = _nearest_indices(ulon_src, ulat_src, lines["u_lon"], lines["u_lat"])
    t_j = xr.DataArray(t_j, dims="boundary_point")
    t_i = xr.DataArray(t_i, dims="boundary_point")
    u_j = xr.DataArray(u_j, dims="boundary_point")
    u_i = xr.DataArray(u_i, dims="boundary_point")

    out_vars = {}
    for name, da in ds.data_vars.items():
        if name in ("tlon", "tlat", "ulon", "ulat"):
            continue
        if not {"nj", "ni"}.issubset(da.dims):
            continue
        j_idx, i_idx = (u_j, u_i) if name in U_POINT_VARS else (t_j, t_i)
        out_vars[name] = da.isel(nj=j_idx, ni=i_idx)

    n = len(lines["t_lon"])
    out = xr.Dataset(
        out_vars,
        coords={
            "boundary_point": np.arange(n),
            "boundary_lon": ("boundary_point", lines["t_lon"]),
            "boundary_lat": ("boundary_point", lines["t_lat"]),
        },
    )

    out_path = Path(outfolder) / f"forcing_obc_segment_{seg_id:03d}.nc"
    out.to_netcdf(out_path)
    return regridders


def process_cice_ic(
    ocn_grid,
    inputdir,
    date_range,
    cice_product_name=None,
    cice_function_name=None,
):
    """
    Generate CICE initial conditions into <inputdir>/ocnice.

    Not implemented yet: CICE IC sourcing (e.g. GLORYS sea-ice fields, or a
    parent CESM/CICE run's own output) isn't wired through raw_data_access
    yet, so this always raises until that work lands. Once it does, this
    becomes a thin wrapper around ic.process_initial_condition(...,
    regrid_fn=<cice regrid step>) -- the same shape mom6.process_mom6_ic uses
    -- with cice_product_name/cice_function_name resolving a CICEForcingProduct
    (see raw_data_access/base.py) instead of raising here.
    """
    raise NotImplementedError(
        "CICE initial condition generation is not implemented yet."
    )


def process_cice_obc(
    hgrid_path,
    inputdir,
    boundaries,
    date_range,
    cice_product_name=None,
    cice_function_name=None,
    variables=None,
    function_args=None,
):
    """
    Generate CICE open boundary conditions into <inputdir>/ocnice.

    Routes through obc.py's shared GET -> chunk -> REGRID -> MERGE engine --
    the same shape mom6.process_mom6_obc/ww3.process_ww3_obc use.

    cice_product_name/cice_function_name default to the raw_data_access
    ``cice_restart`` product/``get_cice_restart_subset`` method -- the only
    CICEForcingProduct registered so far. That product's metadata (fetched
    from the registry, mirroring how mom6.py forwards a GLORYS/MOM6_OUTPUT
    product's metadata as dataset_varnames) is forwarded to the regrid step
    unused for now.

    function_args carries whatever the chosen access function needs beyond
    the generic dates/lat/lon/variables contract -- for cice_restart, that's
    restart_path/grid_path (required) and optionally buffer_deg. There's no
    per-case configurator deriving these yet (unlike MOM6's GLORYS/
    MOM6_OUTPUT product_info), so the caller must supply them directly.

    Runs GET for real (downloading/windowing the restart per boundary) and
    regrids it via _regrid_cice_chunk -- see that function's and
    _cice_boundary_lines's docstrings for the explicit geometry/interpolation
    assumptions this first-pass design rests on.

    The engine's own merge output lands in a private staging directory
    (mirroring ww3.py), then each boundary's merged file is copied into
    <inputdir>/ocnice as ``cice_forcing_obc_segment_NNN.nc`` -- MOM6's OBC
    engine writes ``forcing_obc_segment_NNN.nc`` into that same shared
    directory, so reusing that name here would let one silently clobber
    the other.
    """
    product_name = cice_product_name or "cice_restart"
    function_name = cice_function_name or "get_cice_restart_subset"

    ProductRegistry.load()
    dataset_varnames = ProductRegistry.get_product(product_name).write_metadata()

    staging_dir = Path(inputdir) / "extract_forcings" / "cice"
    raw_dir = staging_dir / "raw_data"
    regridded_dir = staging_dir / "regridded_data"
    merged_dir = staging_dir / "merged"
    output_dir = Path(inputdir) / "ocnice"
    for d in (raw_dir, regridded_dir, merged_dir, output_dir):
        d.mkdir(parents=True, exist_ok=True)

    boundary_number_conversion = {b: i + 1 for i, b in enumerate(boundaries)}
    start_date, end_date = date_range

    obc.process_obc_conditions(
        start_date=start_date,
        end_date=end_date,
        boundary_number_conversion=boundary_number_conversion,
        product_name=product_name,
        function_name=function_name,
        variables=variables,
        extra_args=function_args or {},
        dataset_varnames=dataset_varnames,
        hgrid_path=hgrid_path,
        raw_dataset_path=raw_dir,
        regridded_dataset_path=regridded_dir,
        output_path=merged_dir,
        regrid_chunk_fn=_regrid_cice_chunk,
        get_step_days=None,
        regrid_step_days=None,
    )

    for boundary in boundaries:
        seg_id = boundary_number_conversion[boundary]
        shutil.copy(
            merged_dir / f"forcing_obc_segment_{seg_id:03d}.nc",
            output_dir / f"cice_forcing_obc_segment_{seg_id:03d}.nc",
        )
