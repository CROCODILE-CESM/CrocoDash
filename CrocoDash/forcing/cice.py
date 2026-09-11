"""CICE forcing for CrocoDash: one expanded-grid restart serving as both the
initial condition and the restoring target.

CICE's restoring mechanism (``ice_restoring.F90``) relaxes the
boundary-adjacent ghost cells toward a target ice state over time.
``CICEConfigurator.process`` produces the file that supplies it: the case's
regional domain plus an ``n_halo_cells`` halo on every side, built from a
CICE-shaped forcing product (a real global restart, or a fast synthetic
stand-in -- see ``cice_product_name``/``cice_function_name`` below) regridded
onto every point of that expanded grid. ``configure`` then points CICE's
``ice_ic`` at that file and sets ``restart_ext = .true.``, so CICE reads it as
a restart *including* its ghost ring (``ni = nx_global + 2*nghost``,
``nj = ny_global + 2*nghost`` -- see ``ice_restart.F90``).

The ghost-ring values that land this way are what gets restored toward, given
the restoring-for-OBCs support in Dave Bailey's CICE checkout, which sits on
top of this. Note that stock ``ice_restoring.F90`` does *not* consume that
ring: its active ``restore_ic = 'initial'`` path extrapolates the innermost
physical row/column outward into the ghost cells instead (the commented-out
"easy way", ``aicen_rest = aicen``, is what would use it).

``nghost`` is 1 in CICE (``ice_blocks.F90``), hence ``n_halo_cells``
defaulting to 1: the generated file has to match that extended-restart shape
exactly or CICE won't read it. It stays configurable because the halo also
sets the restoring zone's physical width, but any value other than 1 makes
the file unusable as an ``ice_ic``.

Restoring is opt-in two ways over: pass ``restore_ice=False``, or name
neither product nor function, and ``process`` generates nothing, ``ice_ic``
stays ``'default'``, and CICE runs with zero-gradient boundaries and no
restoring -- a valid configuration, with ice still free to advect out of the
domain. ``restore_ice`` defaults to True, so naming a product is enough to
turn restoring on.

Like a real CICE restart/initial-condition file, the output carries no
``time`` dimension at all -- just the single static snapshot, regridded once
-- on CICE's own ``nj``/``ni`` dimension names, which is what its restart
reader expects.

Unlike MOM6/WW3's OBC, there's no boundary-only regrid and no date-chunking
need (one static snapshot, no real time evolution to fetch incrementally),
so this doesn't route through obc.py's shared GET->chunk->REGRID->MERGE
engine at all -- just resolves the requested product/function via the same
``ProductRegistry`` lookup MOM6/WW3 use (``utils.get_data_access_function``)
instead of hardcoding a single product.

Every variable in the source restart passes through unfiltered (T-point and
U-point alike) -- a superset of the ``aicen``/``vicen``/``vsnon``/``trcrn``
(category-indexed, ncat=5) that ``ice_restoring.F90``'s restoring arrays
actually read. ``uvel``/``vvel`` (B-grid, at the cell corner) are plumbed
through here but not consumed by any restoring path yet; the Consortium
doesn't restore velocity.
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
    # Regridded onto ny/nx here and renamed to CICE's own nj/ni once both
    # point groups are merged (see _regrid_cice_full_grid). The rename can't
    # happen on the target grid itself: the *source* restart already uses
    # nj/ni for its native tripole index space, and xESMF would then have to
    # build an output dataset whose source and target spatial dims collide.
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

    # CICE's restart reader indexes on ni/nj, not the ny/nx the regrid target
    # was built with -- rename now that the source grid's own nj/ni are out of
    # scope, so the file CICE reads through ice_ic has the dims it expects.
    return xr.merge([t_out, u_out]).rename({"ny": "nj", "nx": "ni"})


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
                "the main MOM6 IC/OBC product. The restoring forcing is opt-in: "
                "leaving this unset (None) generates no forcing file and leaves "
                "restore_ice off, so CICE runs with zero-gradient boundaries and "
                "no restoring -- a valid configuration. Set it, together with "
                "cice_function_name, to generate the file: e.g. the real global "
                "restart product 'cice_restart' / 'get_cice_restart_subset' "
                "(raw_data_access/datasets/cice_output.py), which also needs a "
                "real restart_path/grid_path in cice_function_args, or "
                "'reference_ice' / 'get_reference_ice_data' for a fast synthetic "
                "stand-in."
            ),
        ),
        InputValueParam(
            "cice_function_name",
            comment=(
                "Name of the raw_data_access function to call for the CICE "
                "forcing product. Must be given whenever cice_product_name is; "
                "there is no implicit default. See cice_product_name."
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
            comment=(
                "Halo width (T-cells per side) for CICE's restoring forcing. "
                "Must be 1 to match CICE's own nghost, since configure() points "
                "ice_ic at the generated file and CICE reads it with "
                "restart_ext = .true. (ni = nx_global + 2*nghost); any other "
                "value produces a file CICE won't read."
            ),
        ),
        InputValueParam(
            "restore_ice",
            comment=(
                "Whether to restore the boundary-adjacent ghost cells toward the "
                "generated expanded-grid restart. True by default, so naming a "
                "cice_product_name/cice_function_name pair is enough to turn "
                "restoring on. False skips generating the file altogether and "
                "leaves ice_ic at 'default': CICE then runs with zero-gradient "
                "boundaries and no restoring, ice still free to advect out."
            ),
        ),
        InputValueParam(
            "case_inputdir",
            comment=(
                "Case input directory -- where process() writes the forcing file "
                "and therefore the absolute path configure() gives ice_ic."
            ),
        ),
    ]
    output_params = [
        UserNLConfigParam("ice_ic", user_nl_name="cice"),
        UserNLConfigParam("ns_boundary_type", user_nl_name="cice"),
        UserNLConfigParam("ew_boundary_type", user_nl_name="cice"),
        UserNLConfigParam("close_boundaries", user_nl_name="cice"),
        UserNLConfigParam("advect", user_nl_name="cice"),
        UserNLConfigParam("restart_ext", user_nl_name="cice"),
        UserNLConfigParam("restore_ice", user_nl_name="cice"),
        UserNLConfigParam("trestore", user_nl_name="cice"),
    ]

    def __init__(
        self,
        cice_product_name=None,
        cice_function_name=None,
        cice_function_args=None,
        n_halo_cells=1,
        restore_ice=True,
        case_inputdir=None,
    ):
        super().__init__(
            cice_product_name=cice_product_name,
            cice_function_name=cice_function_name,
            cice_function_args=cice_function_args or {},
            n_halo_cells=n_halo_cells,
            restore_ice=restore_ice,
            case_inputdir=case_inputdir,
        )

    def validate_args(self, **kwargs):
        super().validate_args(**kwargs)

        # None means "generate no restoring forcing at all" -- process() skips
        # itself entirely and configure() leaves restore_ice off. Anything else
        # must be a registered CICE forcing product: process() regrids it with
        # CICEForcingProduct's own B-grid var-name metadata, so a MOM6 (or any
        # other) forcing product can't stand in here.
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

    def _resolve_forcing_source(self):
        """(product_name, function_name) for the restoring forcing, or
        (None, None) when the caller asked for none.

        Restoring is opt-in: CICE runs perfectly well without it (zero-gradient
        boundaries, no restoring), so naming neither product nor function means
        "generate nothing". Defaulting to the real ``cice_restart`` product
        instead would make every CICE case depend on a real global
        restart_path/grid_path most users don't have, to produce a restoring
        target they may not have asked for.

        Half-specified is always a mistake -- a typo'd or forgotten argument --
        so it raises rather than silently skipping behind a case that still
        runs. That check runs before the ``restore_ice`` gate below, so an
        explicit ``restore_ice=False`` doesn't swallow the typo.
        """
        product_name = self.get_input_param("cice_product_name")
        function_name = self.get_input_param("cice_function_name")

        if product_name and function_name and not self.get_input_param("restore_ice"):
            return None, None

        if not product_name and not function_name:
            return None, None

        if not product_name or not function_name:
            missing, given = (
                ("cice_product_name", "cice_function_name")
                if not product_name
                else ("cice_function_name", "cice_product_name")
            )
            raise ValueError(
                f"CICE restoring forcing needs both cice_product_name and "
                f"cice_function_name; {given} was given but {missing} was not. "
                f"Pass both to generate the forcing file, or neither to run CICE "
                f"without restoring."
            )

        return product_name, function_name

    def configure(self):
        self.set_output_param("ns_boundary_type", "'zero_gradient'")
        self.set_output_param("ew_boundary_type", "'zero_gradient'")
        self.set_output_param("close_boundaries", ".false.")
        self.set_output_param("advect", "'upwind'")
        # Set unconditionally, not just when restoring: CICE's own
        # set_nml.bczerogradient option pairs zero_gradient boundaries with
        # restart_ext = .true., and it's what makes the ghost ring exist on
        # disk at all -- which is what ice_ic needs below. Harmless without
        # restoring, since ice_ic = 'default' means no restart is read.
        self.set_output_param("restart_ext", ".true.")

        # The namelist restore_ice tracks whether process() will actually
        # produce the domain+halo restart to restore toward -- turning it on
        # without that file would point CICE at a restoring target that
        # doesn't exist. So it's the *conjunction* of the caller's restore_ice
        # and a named product, not the input flag alone. trestore is CICE's own
        # documented default timescale, and is inert when restore_ice is off.
        product_name, _ = self._resolve_forcing_source()
        restoring = bool(product_name)
        self.set_output_param("restore_ice", ".true." if restoring else ".false.")
        self.set_output_param("trestore", 90)

        # ice_ic points at the expanded-grid restart process() writes, so its
        # ghost ring is read in (restart_ext above) and becomes the restoring
        # target. 'default' -- CICE's own latitude/SST-dependent internal
        # initialization -- whenever there's no such file to point at.
        self.set_output_param(
            "ice_ic", f"'{self._forcing_filepath()}'" if restoring else "'default'"
        )
        super().configure()

    def _forcing_filepath(self):
        """Absolute path process() writes the forcing file to.

        Needed at configure() time (before process() has run) to give ice_ic a
        path, so it's derived from case_inputdir rather than the WorkflowContext
        process() gets. get_output_filepaths() resolves the same file from the
        directory it's handed instead, since bundling relocates it.
        """
        case_inputdir = self.get_input_param("case_inputdir")
        if not case_inputdir:
            raise ValueError(
                "CICE restoring is on (restore_ice, cice_product_name and "
                "cice_function_name are all set) but case_inputdir is unset, so "
                "there's no path to give ice_ic. It's injected automatically from "
                "the Case; pass it explicitly when constructing "
                "CICEConfigurator directly."
            )
        return Path(case_inputdir) / SEA_ICE_SUBDIR / FORCING_FILENAME

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

        Does nothing unless the caller named both ``cice_product_name`` and
        ``cice_function_name`` -- restoring is opt-in, see
        ``_resolve_forcing_source``.

        When they are given, covers the case's domain plus an
        ``n_halo_cells``-cell halo on every side (grown via
        ``SupergridBase.expand``), windowed from that CICE forcing product
        (resolved via the same ``ProductRegistry`` lookup MOM6/WW3 use --
        ``restart_path``/``grid_path`` for the real ``cice_restart`` product go
        in ``cice_function_args``) and regridded onto that expanded grid. Like
        a real CICE restart/initial-condition file, the output has no
        ``time`` dimension -- a single static snapshot (for ``cice_restart``),
        not a time series.
        """
        product_name, function_name = self._resolve_forcing_source()
        if product_name is None:
            print(
                "[info] CICE: no cice_product_name/cice_function_name given -- "
                "skipping the restoring forcing file. CICE will run with "
                "zero-gradient boundaries and restore_ice off. Pass both to "
                "generate it."
            )
            return

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
