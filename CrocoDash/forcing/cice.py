"""CICE forcing for CrocoDash: a single expanded-grid restoring file.

CICE's restoring mechanism (``ice_restoring.F90``) relaxes boundary-adjacent
cells toward a target ice state over time -- the user is separately
extending that Fortran to read the restoring target from an external file
(not visible in this repo yet). ``CICEConfigurator.process`` produces that
file: it must cover the case's regional domain plus a halo (``n_halo_cells``
on every side, required for the restoring routine), built from a CICE-shaped
forcing product (real global restart, or a fast synthetic stand-in -- see
``cice_product_name``/``cice_function_name`` below) regridded onto every
point of that expanded grid. Like a real CICE restart/initial-condition
file, the output carries no ``time`` dimension at all -- just the single
static snapshot (for ``cice_restart``), regridded once.

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
from CrocoDash.forcing import utils
from CrocoDash.forcing.base import *
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import CICEForcingProduct

# Where process() writes CICE's forcing file, and therefore where
# get_output_filepaths() looks for it. Kept in one place so the writer and the
# reader cannot drift apart.
SEA_ICE_SUBDIR = "sea_ice"
FORCING_FILENAME = "cice_forcing.nc"

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
        ds["tlon"].values,
        ds["tlat"].values,
        grid.tlon.values,
        grid.tlat.values,
    )
    u_out = _regrid_point_group(
        ds,
        u_vars,
        ds["ulon"].values,
        ds["ulat"].values,
        grid.qlon.values[1:, :-1],
        grid.qlat.values[1:, :-1],
    )
    if u_vars:
        u_out = u_out.rename({"lon": "u_lon", "lat": "u_lat"})

    return xr.merge([t_out, u_out])


@register
class CICEConfigurator(BaseConfigurator):
    name = "CICE"
    process_components = {"cice": "process"}
    required_for_compsets = ["CICE"]
    allowed_compsets = ["CICE"]
    input_params = [
        InputValueParam(
            "cice_product_name",
            comment=(
                "Name of the CICE forcing data product, mirroring "
                "Case.configure_forcings's product_name/function_name pattern for "
                "the main MOM6 IC/OBC product. Defaults (None) to the real global "
                "restart product ('cice_restart', "
                "raw_data_access/datasets/cice_output.py), which requires a real "
                "restart_path/grid_path (see cice_function_args). Pass a "
                "different product name (e.g. 'reference_ice') to source CICE's "
                "forcing some other way instead."
            ),
        ),
        InputValueParam(
            "cice_function_name",
            comment=(
                "Name of the raw_data_access function to call for the CICE "
                "forcing product. Defaults (None) to 'get_cice_restart_subset'. "
                "See cice_product_name."
            ),
        ),
        InputValueParam(
            "cice_function_args",
            comment=(
                "Extra kwargs the chosen product's access function needs (e.g. "
                "restart_path/grid_path for 'cice_restart'; none for "
                "'reference_ice')."
            ),
        ),
        InputValueParam(
            "n_halo_cells",
            comment="Halo width (T-cells per side) for CICE's restoring forcing",
        ),
    ]
    output_params = [
        UserNLConfigParam("ice_ic", user_nl_name="cice"),
        UserNLConfigParam("ns_boundary_type", user_nl_name="cice"),
        UserNLConfigParam("ew_boundary_type", user_nl_name="cice"),
        UserNLConfigParam("close_boundaries", user_nl_name="cice"),
        UserNLConfigParam("advect", user_nl_name="cice"),
        UserNLConfigParam("restore_ice", user_nl_name="cice"),
        UserNLConfigParam("trestore", user_nl_name="cice"),
    ]

    def __init__(
        self,
        cice_product_name=None,
        cice_function_name=None,
        cice_function_args=None,
        n_halo_cells=2,
    ):
        super().__init__(
            cice_product_name=cice_product_name,
            cice_function_name=cice_function_name,
            cice_function_args=cice_function_args or {},
            n_halo_cells=n_halo_cells,
        )

    def validate_args(self, **kwargs):
        super().validate_args(**kwargs)

        # None means "use this class's default product", resolved in process().
        # Anything else must be a registered CICE forcing product: process()
        # regrids it with CICEForcingProduct's own B-grid var-name metadata, so
        # a MOM6 (or any other) forcing product can't stand in here.
        product_name = kwargs["cice_product_name"]
        if product_name:
            ProductRegistry.load()
            if not ProductRegistry.product_exists(product_name):
                raise ValueError(
                    f"Unknown forcing product '{product_name}'. Known products: "
                    f"{sorted(ProductRegistry.products)}."
                )
            if not ProductRegistry.product_is_of_type(product_name, CICEForcingProduct):
                raise ValueError(
                    f"Product '{product_name}' ({ProductRegistry.get_product(product_name).__name__}) "
                    "is not a CICEForcingProduct, so it can't be used as cice_product_name "
                    "(CICE's restoring forcing). If this is a MOM6 initial/boundary condition "
                    "product, pass it as product_name instead."
                )

    def configure(self):
        self.set_output_param("ice_ic", "'default'")
        self.set_output_param("ns_boundary_type", "'zero_gradient'")
        self.set_output_param("ew_boundary_type", "'zero_gradient'")
        self.set_output_param("close_boundaries", ".false.")
        self.set_output_param("advect", "'upwind'")
        # Enables restoring toward the domain+halo forcing file generated by
        # this class's process() method at CICE's own documented default
        # timescale. The file/variable contract the not-yet-merged CICE
        # restoring-file reader will expect is unverified (see this module's
        # docstring), so the generated file's path isn't wired to a
        # namelist parameter here yet.
        self.set_output_param("restore_ice", ".true.")
        self.set_output_param("trestore", 90)
        super().configure()

    def get_output_filepaths(self, ocn_ice_directory):
        """CICE's forcing file, which lives beside ocnice/ rather than in it.

        The base implementation walks output_params for is_file entries, but all
        of CICE's are namelist settings -- the forcing file's location is fixed
        by process() rather than carried in a parameter. Without this override
        the base returns nothing, so CaseBundle.bundle() copies no CICE file at
        all and validate_output_filepaths() passes vacuously.

        ocn_ice_directory is <inputdir>/ocnice; process() writes to
        <inputdir>/sea_ice, hence the sibling lookup.
        """
        path = Path(ocn_ice_directory).parent / SEA_ICE_SUBDIR / FORCING_FILENAME
        return [path] if path.exists() else []

    def process(self, ctx):
        """
        Generate CICE's single restoring forcing file into
        <inputdir>/sea_ice/cice_forcing.nc.

        Covers the case's domain plus an ``n_halo_cells``-cell halo on every
        side (grown via ``SupergridBase.expand``), windowed from the requested
        CICE forcing product (``cice_product_name``/``cice_function_name``,
        resolved via the same ``ProductRegistry`` lookup MOM6/WW3 use --
        ``restart_path``/``grid_path`` for the real ``cice_restart`` product go
        in ``cice_function_args``) and regridded onto that expanded grid. Like
        a real CICE restart/initial-condition file, the output has no
        ``time`` dimension -- a single static snapshot (for ``cice_restart``),
        not a time series.
        """
        hgrid_ds = xr.open_dataset(ctx.supergrid_path)
        grid = Grid.from_supergrid_ds(hgrid_ds)
        n_halo_cells = self.get_input_param("n_halo_cells")
        grid.supergrid = grid.supergrid.expand(n_halo_cells)

        bbox = Grid.get_bounding_boxes(grid)["ic"]

        raw_dir = Path(ctx.inputdir) / "extract_forcings" / "cice" / "raw_data"
        raw_dir.mkdir(parents=True, exist_ok=True)
        output_dir = Path(ctx.inputdir) / SEA_ICE_SUBDIR
        output_dir.mkdir(parents=True, exist_ok=True)

        conditions = ctx.config["conditions"]
        date_range = (
            conditions["inputs"]["start_date"],
            conditions["inputs"]["end_date"],
        )

        product_name = self.get_input_param("cice_product_name") or "cice_restart"
        function_name = (
            self.get_input_param("cice_function_name") or "get_cice_restart_subset"
        )
        data_access_fn = utils.get_data_access_function(product_name, function_name)
        subset_paths = data_access_fn(
            dates=date_range,
            output_folder=raw_dir,
            lat_min=bbox["lat_min"] - 1,
            lat_max=bbox["lat_max"] + 1,
            lon_min=bbox["lon_min"] - 1,
            lon_max=bbox["lon_max"] + 1,
            **(self.get_input_param("cice_function_args") or {}),
        )
        subset = xr.open_dataset(subset_paths[0])
        if "time" in subset.dims:
            # A CICE restart/initial-condition file is a single static
            # snapshot -- no `time` dimension at all, unlike a real dated
            # forcing stream. Upstream products carry one anyway (to keep a
            # uniform GET-step return shape); drop it here before regridding.
            #
            # Short-term: this restoring file is currently a single static
            # snapshot because that's all the current upstream products
            # (cice_restart/reference_ice) provide. Once the Fortran
            # restoring-file reader and a real dated CICE forcing product
            # exist, this file will likely need a genuine time-varying
            # restoring target again -- revisit dropping `time` here then.
            subset = subset.isel(time=0, drop=True)

        regridded = _regrid_cice_full_grid(subset, grid)

        # Land/masked cells come back as NaN from the nearest-neighbor
        # regrid -- CICE restart/initial files use zero for land, not a
        # _FillValue convention (which isn't really defined for restarts).
        regridded = regridded.fillna(0)

        # xarray's auto-generated "coordinates" attribute would otherwise
        # list every non-dimension coordinate whose dims are a subset of a
        # variable's own (lat/lon *and* u_lat/u_lon, since the T-point and
        # U-point groups share dim names) -- every variable just gets "lat
        # lon" instead. Set via .encoding (not .attrs) so
        # conventions.encode_dataset_coordinates does the CF-correct thing
        # with it before the plain _FillValue encoding below is applied.
        for var in regridded.data_vars:
            regridded[var].encoding["coordinates"] = "lat lon"
        # Demote u_lat/u_lon from coordinate to plain-variable status now
        # that no variable's "coordinates" attribute references them --
        # otherwise xarray writes them as an orphaned *global* "coordinates"
        # attribute to avoid silently dropping them.
        u_point_coords = [c for c in ("u_lat", "u_lon") if c in regridded.coords]
        if u_point_coords:
            regridded = regridded.reset_coords(u_point_coords)

        # _FillValue isn't a real restart-file convention either -- suppress
        # it on every variable, including the lat/lon/u_lat/u_lon coordinate
        # arrays themselves (which xarray would otherwise tag with it too,
        # even though they're fully populated with no missing values).
        encoding = {var: {"_FillValue": None} for var in regridded.variables}
        regridded.to_netcdf(output_dir / FORCING_FILENAME, encoding=encoding)
