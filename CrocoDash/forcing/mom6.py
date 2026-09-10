"""MOM6 initial + open boundary condition configuration and processing.

``ConditionsConfigurator`` is always active for regional MOM6 cases -- it
builds the `user_nl_mom` initial condition and OBC_SEGMENT_* parameters at
configure time, and (one-to-many: this one configurator answers for both
the "ic" and "bc" process flags) drives IC/OBC extraction at process time via
``forcing.ic``/``forcing.obc``'s model-agnostic engines, supplying MOM6's own
regrid step -- built on ``regional_mom6``'s ``segment``/``experiment``
classes and ``mom6_forge``'s fill utilities -- and the MOM6-specific piece of
the GET step (turning a forcing product's own u/v/eta/tracer var-name
metadata into a download request).
"""

import os
from datetime import datetime
from functools import partial
from pathlib import Path

import dask
import netCDF4
import regional_mom6 as rm6
import mom6_forge as m6b
import xarray as xr
from CrocoDash import logging
from CrocoDash.forcing import ic as ic_mod, obc, utils
from CrocoDash.forcing.base import *
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import Calendar, MOM6ForcingProduct

logger = logging.setup_logger(__name__)


def build_forcing_request(
    product_info: dict, function_args: dict = None
) -> tuple[list, dict]:
    """Build the (variables, extra_args) an access function needs from a MOM6
    forcing product_info dict (u/v/eta/tracer var names).

    function_args: user overrides (or access-function defaults) for the access
    function's non-required arguments, as written to config.json's
    forcing.function_args by configure_forcings()'s function_overrides. Merged
    into extra_args last so they take precedence over product_info-derived keys.
    """
    phys_vars = [
        product_info["u_var_name"],
        product_info["v_var_name"],
        product_info["eta_var_name"],
        product_info["tracer_var_names"]["temp"],
        product_info["tracer_var_names"]["salt"],
    ]
    extra_tracers = [
        v
        for k, v in product_info["tracer_var_names"].items()
        if k not in ("temp", "salt")
    ]
    variables = phys_vars + extra_tracers
    extra_args = {
        key: product_info[key]
        for key in ("dataset_path", "date_format", "regex", "delimiter")
        if key in product_info
    }
    extra_args.update(function_args or {})
    return variables, extra_args


# ---------------------------------------------------------------------------
# OBC regrid step
# ---------------------------------------------------------------------------


def _regrid_obc_chunk(
    ds, hgrid, boundary, seg_id, outfolder, dataset_varnames, start_date, regridders
):
    """Regrid one OBC chunk via regional_mom6's Segment. Writes to
    ``outfolder / f"forcing_obc_segment_{seg_id:03d}.nc"`` -- the filename
    ``obc.py``'s generic engine expects to rename per-chunk.

    ``Segment.regrid_velocity_tracers`` only reads from disk (it calls
    ``xr.open_mfdataset`` on ``infile`` internally), so unlike the engine that
    handed us ``ds``, we do need a real file here -- write one, use it, clean
    it up. That's this function's own business, not the generic engine's.
    """
    outfolder = Path(outfolder)
    tmp_file = outfolder / f"_tmp_{boundary}_segment_{seg_id:03d}.nc"
    # Serialised deliberately. This dataset is dask-backed, and writing it
    # through dask's threaded scheduler deadlocks intermittently inside
    # HDF5: a CrocoDash domain sweep in crocontainer wedged here on 3 of 16
    # domains in one run and a disjoint 4 of 16 in the next, always with the
    # main thread parked in dask.local.queue_get waiting on a worker that
    # never returns. Which domain hits it is random -- the topology is not
    # the trigger. Same guard, same reason as _download_initial_condition
    # in ic.py; the chunk-by-chunk memory profile is unchanged.
    with dask.config.set(scheduler="synchronous"):
        ds.to_netcdf(tmp_file)
    try:
        seg = rm6.segment(
            hgrid=hgrid,
            bathymetry_path=None,
            outfolder=outfolder,
            segment_name=f"segment_{seg_id:03d}",
            orientation=boundary,
            startdate=start_date,
            repeat_year_forcing=False,
        )
        seg.regrid_velocity_tracers(
            infile=tmp_file,
            varnames=dataset_varnames,
            arakawa_grid=None,
            regridding_method="bilinear",
            fill_method=rm6.regridding.fill_missing_data,
            regridders=regridders,
            calendar=dataset_varnames["calendar"]["mom6"],
            time_units=dataset_varnames["time_units"],
            # Opt in to ESMF skipping degenerate (duplicate/collapsed) source
            # cells rather than aborting the regrid with "rc=506 (Degenerate
            # Element Detected)". Global products have them near the poles --
            # GLORYS at its southernmost latitudes -- so polar domains fail
            # outright without this. rm6 defaults it off so a source grid that
            # is malformed for some other reason still fails loudly.
            ignore_degenerate=True,
        )
        return seg.regridders
    finally:
        tmp_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# IC regrid step
# ---------------------------------------------------------------------------


def _split_bgc_tracers_into_files(
    output_path, boundary_number_conversion: dict, marbl_var_names: dict
):
    """Move each BGC tracer out of the per-boundary OBC files into its own file.

    MOM6's generic tracer code reads BGC open-boundary data from one file per
    tracer holding every segment (``<tracer>_obc_segment.nc``), whereas the
    physical tracers are read per boundary from
    ``forcing_obc_segment_NNN.nc``. The regrid step writes the BGC tracers into
    those per-boundary files alongside temp/salt, so without this step the
    per-tracer files MOM6 is pointed at never exist.

    The tracers are *moved*, not copied: ``OBC_SEGMENT_NNN_DATA`` names only
    U/V/SSH/TEMP/SALT out of the per-boundary file, so BGC copies left behind
    there are never read and would put every field on disk twice.

    Mirrors regional_mom6's ``reformat_bgc_tracers_into_files``, which only runs
    inside rm6's own ``setup_ocean_state_boundaries`` and so is never reached by
    this pipeline.
    """
    if not marbl_var_names:
        return []

    output_path = Path(output_path)
    seg_ids = [f"{n:03d}" for n in boundary_number_conversion.values()]
    seg_files = {seg: output_path / f"forcing_obc_segment_{seg}.nc" for seg in seg_ids}
    out_files = [output_path / f"{var}_obc_segment.nc" for var in marbl_var_names]

    # Step 3 strips the BGC tracers out of the per-boundary files, so on a
    # re-run they are no longer there to be read. Every other phase of the OBC
    # pipeline resumes by skipping completed work; do the same here.
    if all(f.exists() for f in out_files):
        logger.info("BGC SPLIT: per-tracer files already exist. Skipping.")
        return out_files

    # 1. Open each per-boundary file once. These are the largest files the
    #    pipeline produces, and opening inside the tracer loop below would
    #    reopen every one of them once per tracer.
    seg_datasets = {seg: xr.open_dataset(f) for seg, f in seg_files.items()}

    # 2. Write one file per tracer, gathering that tracer across all segments.
    written = []
    try:
        for var in marbl_var_names:
            ds_var = xr.Dataset()
            for seg in seg_ids:
                ds = seg_datasets[seg]
                var_name = f"{var}_segment_{seg}"
                if var_name not in ds:
                    raise KeyError(
                        f"BGC tracer variable {var_name!r} not found in "
                        f"{seg_files[seg]}. Expected it there because {var!r} was "
                        "included in the regridded tracer set."
                    )
                # Left lazy so to_netcdf streams from the open source file
                # rather than materialising every segment first.
                ds_var[var_name] = ds[var_name]
                dz_var_name = f"dz_{var_name}"
                if dz_var_name in ds:
                    ds_var[dz_var_name] = ds[dz_var_name]

            out_file = output_path / f"{var}_obc_segment.nc"
            ds_var.to_netcdf(out_file, unlimited_dims="time")
            written.append(out_file)
            logger.info("BGC SPLIT: wrote %s", out_file.name)
    finally:
        for ds in seg_datasets.values():
            ds.close()

    # 3. Drop the now-redundant copies from the per-boundary files. Must follow
    #    step 2, which streams its output from these same files.
    for seg in seg_ids:
        seg_file = seg_files[seg]
        with xr.open_dataset(seg_file) as ds:
            drop = [
                name
                for var in marbl_var_names
                for name in (f"{var}_segment_{seg}", f"dz_{var}_segment_{seg}")
                if name in ds
            ]
            if not drop:
                continue
            # A NetCDF file cannot be rewritten while open, so stage a copy and
            # swap it in. os.replace is atomic: an interrupted run leaves either
            # the old file or the new one, never a truncated one.
            tmp = seg_file.with_name(seg_file.name + ".tmp")
            ds.drop_vars(drop).to_netcdf(tmp, unlimited_dims="time")
        os.replace(tmp, seg_file)
        logger.info("BGC SPLIT: dropped %d BGC vars from %s", len(drop), seg_file.name)

    return written


def _fill_missing_and_write(input_path, output_path, var_specs, z_dim="zl"):
    """Fill masked-missing data and interpolation gaps for each variable, then write.

    var_specs: list of dicts with keys:
        name: variable name in the dataset
        mask: mom6_forge Topo mask array (tmask/umask/vmask) for this variable
        dims: (x_dim, y_dim) or (x_dim, y_dim, z_dim) passed to final_cleanliness_fill
        encoding: netCDF encoding dict for this variable
    """
    ds = xr.open_dataset(input_path, mask_and_scale=True)
    encoding = {}
    for spec in var_specs:
        name, mask, dims = spec["name"], spec["mask"], spec["dims"]
        if len(dims) == 3:
            for z_ind in range(ds[z_dim].shape[0]):
                ds[name][z_ind] = m6b.utils.fill_missing_data(
                    ds[name][z_ind].values, mask.values
                )
        else:
            ds[name][:] = m6b.utils.fill_missing_data(ds[name].values, mask.values)
        ds[name] = final_cleanliness_fill(ds[name], *dims)
        encoding[name] = spec["encoding"]
    ds = ds.fillna(0)
    ds.to_netcdf(output_path, encoding=encoding)


def final_cleanliness_fill(var, x_dim, y_dim, z_dim=None):
    var = (
        var.where(var != 0)  # convert 0.0 → NaN
        .interpolate_na(x_dim, method="linear")  # interpolate along x
        .ffill(x_dim)
        .bfill(x_dim)
        .ffill(y_dim)  # fill along y
        .bfill(y_dim)
    )
    if z_dim is not None:
        var = var.ffill(z_dim)
    return var


def _regrid_ic(
    raw_file,
    hgrid,
    start_date,
    output_dir,
    dataset_varnames,
    hgrid_path,
    vgrid_path,
    bathymetry_path,
):
    """MOM6's IC regrid step. hgrid_path/vgrid_path/bathymetry_path aren't
    part of ic.py's generic engine signature -- process_ic below binds them
    via functools.partial before handing this to the engine as regrid_fn."""
    expt = rm6.experiment.create_empty()
    # hgrid/vgrid are read-only properties derived from m6f_hgrid/m6f_vgrid
    # (mom6_forge Grid/VGrid objects) -- set those instead. _make_vgrid
    # already sets m6f_vgrid as a side effect.
    expt.m6f_hgrid = Grid.from_supergrid_ds(hgrid)
    expt.mom_input_dir = output_dir
    expt.date_range = [start_date, None]
    vgrid_from_file = xr.open_dataset(vgrid_path)
    expt._make_vgrid(vgrid_from_file.dz.data)

    eta_path = expt.mom_input_dir / "init_eta.nc"
    if eta_path.exists():
        if not utils.is_valid_netcdf(eta_path):
            raise RuntimeError(
                f"{eta_path} exists but is not valid NetCDF. Delete it and re-run."
            )
        logger.info("Initial condition files already exist. They will be skipped.")
    else:
        expt.setup_initial_condition(raw_file, dataset_varnames, arakawa_grid=None)

    eta_filled_path = expt.mom_input_dir / "init_eta_filled.nc"
    if eta_filled_path.exists():
        if not utils.is_valid_netcdf(eta_filled_path):
            raise RuntimeError(
                f"{eta_filled_path} exists but is not valid NetCDF. Delete it and re-run."
            )
        logger.info(
            "Initial condition filled files already exist. They will be skipped."
        )
        return

    # Add the M6b Fill method onto the initial conditions
    logger.info("Start mom6_forge fill...")
    grid = Grid.from_supergrid(hgrid_path)

    with xr.open_dataset(bathymetry_path) as ds:
        min_depth = ds.attrs.get("min_depth")
    bathymetry = Topo.from_topo_file(
        grid=grid, topo_file_path=bathymetry_path, min_depth=min_depth
    )

    # ETA - no depth
    _fill_missing_and_write(
        output_dir / "init_eta.nc",
        output_dir / "init_eta_filled.nc",
        [
            {
                "name": "eta_t",
                "mask": bathymetry.tmask,
                "dims": ("nx", "ny"),
                "encoding": {"_FillValue": None},
            },
        ],
    )

    # Velocity
    _fill_missing_and_write(
        output_dir / "init_vel.nc",
        output_dir / "init_vel_filled.nc",
        [
            {
                "name": "u",
                "mask": bathymetry.umask,
                "dims": ("nxp", "ny", "zl"),
                "encoding": {"_FillValue": netCDF4.default_fillvals["f4"]},
            },
            {
                "name": "v",
                "mask": bathymetry.vmask,
                "dims": ("nx", "nyp", "zl"),
                "encoding": {"_FillValue": netCDF4.default_fillvals["f4"]},
            },
        ],
    )

    # Tracers
    _fill_missing_and_write(
        output_dir / "init_tracers.nc",
        output_dir / "init_tracers_filled.nc",
        [
            {
                "name": var,
                "mask": bathymetry.tmask,
                "dims": ("nx", "ny", "zl"),
                "encoding": {"_FillValue": -1e20, "missing_value": -1e20},
            }
            for var in ["temp", "salt"]
        ],
    )
    logger.info("...end mom6_forge fill.")


@register
class ConditionsConfigurator(BaseConfigurator):
    """Initial condition + open boundary condition (OBC) setup for MOM6.

    Always active for regional MOM6 cases. Builds the `user_nl_mom` initial
    condition and OBC_SEGMENT_* parameters, and the derived values consumed
    by process_ic/process_bc (dates, forcing product metadata, boundary
    numbering).
    """

    name = "conditions"
    required_for_compsets = ["MOM6"]
    process_components = {"ic": "process_ic", "bc": "process_bc"}

    _DATE_FORMAT = "%Y%m%d"

    # Static output params that don't vary by boundary count.
    _IC_PARAM_NAMES = {
        "INIT_LAYERS_FROM_Z_FILE",
        "Z_INIT_ALE_REMAPPING",
        "TEMP_SALT_INIT_VERTICAL_REMAP_ONLY",
        "DEPRESS_INITIAL_SURFACE",
        "VELOCITY_CONFIG",
        "TEMP_SALT_Z_INIT_FILE",
        "SURFACE_HEIGHT_IC_FILE",
        "VELOCITY_FILE",
        "Z_INIT_FILE_PTEMP_VAR",
        "Z_INIT_FILE_SALT_VAR",
        "SURFACE_HEIGHT_IC_VAR",
        "U_IC_VAR",
        "V_IC_VAR",
    }

    input_params = [
        InputValueParam("start_date", comment="Forcing start date"),
        InputValueParam("end_date", comment="Forcing end date"),
        InputValueParam("boundaries", comment="List of open boundaries to process"),
        InputValueParam("product_name", comment="Forcing data product name"),
        InputValueParam(
            "function_name", comment="Download function name for the product"
        ),
        InputValueParam(
            "compset", comment="Compset lname, used to detect MARBL tracers"
        ),
        InputValueParam(
            "function_args",
            comment="Resolved (defaults + overrides) args for the download function",
        ),
    ]

    output_params = [
        # Initial conditions
        UserNLConfigParam("INIT_LAYERS_FROM_Z_FILE", comment="Initial conditions"),
        UserNLConfigParam("Z_INIT_ALE_REMAPPING", comment="Initial conditions"),
        UserNLConfigParam(
            "TEMP_SALT_INIT_VERTICAL_REMAP_ONLY", comment="Initial conditions"
        ),
        UserNLConfigParam("DEPRESS_INITIAL_SURFACE", comment="Initial conditions"),
        UserNLConfigParam("VELOCITY_CONFIG", comment="Initial conditions"),
        UserNLConfigParam("TEMP_SALT_Z_INIT_FILE", comment="Initial conditions"),
        UserNLConfigParam("SURFACE_HEIGHT_IC_FILE", comment="Initial conditions"),
        UserNLConfigParam("VELOCITY_FILE", comment="Initial conditions"),
        UserNLConfigParam("Z_INIT_FILE_PTEMP_VAR", comment="Initial conditions"),
        UserNLConfigParam("Z_INIT_FILE_SALT_VAR", comment="Initial conditions"),
        UserNLConfigParam("SURFACE_HEIGHT_IC_VAR", comment="Initial conditions"),
        UserNLConfigParam("U_IC_VAR", comment="Initial conditions"),
        UserNLConfigParam("V_IC_VAR", comment="Initial conditions"),
        # Open boundary conditions (static; per-boundary params are added dynamically)
        UserNLConfigParam("OBC_NUMBER_OF_SEGMENTS", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_FREESLIP_VORTICITY", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_FREESLIP_STRAIN", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_COMPUTED_VORTICITY", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_COMPUTED_STRAIN", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_ZERO_BIHARMONIC", comment="Open boundary conditions"),
        UserNLConfigParam(
            "OBC_TRACER_RESERVOIR_LENGTH_SCALE_OUT", comment="Open boundary conditions"
        ),
        UserNLConfigParam(
            "OBC_TRACER_RESERVOIR_LENGTH_SCALE_IN", comment="Open boundary conditions"
        ),
        UserNLConfigParam("BRUSHCUTTER_MODE", comment="Open boundary conditions"),
        # Derived, config.json-only values consumed by process_ic/process_bc.
        # No case-side effect (see ConfigOutputParam).
        ConfigOutputParam(
            "date_format", comment="strftime format used for dates in config.json"
        ),
        ConfigOutputParam("information", comment="Product variable-name metadata"),
        ConfigOutputParam(
            "get_step_days", comment="Chunk size (days) for forcing retrieval (GET)"
        ),
        ConfigOutputParam(
            "regrid_step_days", comment="Chunk size (days) for forcing regridding"
        ),
        ConfigOutputParam(
            "boundary_number_conversion",
            comment="Boundary name -> MOM6 segment number",
        ),
        ConfigOutputParam(
            "preview", comment="Whether process_ic/process_bc should preview only"
        ),
        ConfigOutputParam(
            "function_args",
            comment="Resolved (defaults + overrides) args for the download function",
        ),
    ]

    def __init__(
        self,
        boundaries,
        product_name,
        function_name,
        compset,
        date_range=None,
        start_date=None,
        end_date=None,
        function_args=None,
    ):
        if date_range is not None:
            start_date = date_range[0].strftime(self._DATE_FORMAT)
            end_date = date_range[1].strftime(self._DATE_FORMAT)
        super().__init__(
            start_date=start_date,
            end_date=end_date,
            boundaries=boundaries,
            product_name=product_name,
            function_name=function_name,
            compset=compset,
            function_args=function_args or {},
        )

    def validate_args(self, **kwargs):
        super().validate_args(**kwargs)

        boundaries = kwargs["boundaries"]
        if not isinstance(boundaries, list):
            raise TypeError("boundaries must be a list of strings.")
        if not all(isinstance(boundary, str) for boundary in boundaries):
            raise TypeError("boundaries must be a list of strings.")

        ProductRegistry.load()
        product_name = kwargs["product_name"]
        if not ProductRegistry.product_exists(product_name):
            raise ValueError(
                f"Unknown forcing product '{product_name}'. Known products: "
                f"{sorted(ProductRegistry.products)}."
            )
        if not ProductRegistry.product_is_of_type(product_name, MOM6ForcingProduct):
            raise ValueError(
                f"Product '{product_name}' ({ProductRegistry.get_product(product_name).__name__}) "
                "is not a MOM6ForcingProduct, so it can't be used as the conditions configurator's product_name "
                "(MOM6's initial/boundary condition forcing). If this is a CICE forcing product, pass it as cice_product_name instead."
            )

    @staticmethod
    def _segment_index(boundaries, boundary):
        """Map a boundary name to its 1-based MOM6 segment number (or the inverse)."""
        direction_dir = {b: i + 1 for i, b in enumerate(boundaries)}
        direction_dir_inv = {v: k for k, v in direction_dir.items()}
        merged = {**direction_dir, **direction_dir_inv}
        try:
            return merged[boundary]
        except KeyError:
            raise ValueError(
                "Invalid direction or segment number for MOM6 rectangular orientation"
            )

    def configure(self):
        start_date = self.get_input_param("start_date")
        end_date = self.get_input_param("end_date")
        boundaries = self.get_input_param("boundaries")
        product_name = self.get_input_param("product_name").lower()
        compset = self.get_input_param("compset")
        product = ProductRegistry.get_product(product_name)

        # ---- derived, config.json-only values ----
        self.set_output_param("date_format", self._DATE_FORMAT)
        self.set_output_param(
            "information",
            product.write_metadata(include_marbl_tracers="%MARBL" in compset),
        )
        start_dt = datetime.strptime(start_date, self._DATE_FORMAT)
        end_dt = datetime.strptime(end_date, self._DATE_FORMAT)

        # Setting both get and regrid to the entire modeling period. Power users can modify this as they need!
        step = (end_dt - start_dt).days + 1
        self.set_output_param("get_step_days", step)
        self.set_output_param("regrid_step_days", step)
        self.set_output_param(
            "boundary_number_conversion",
            {b: i + 1 for i, b in enumerate(boundaries)},
        )
        self.set_output_param("preview", False)
        self.set_output_param("function_args", self.get_input_param("function_args"))

        # ---- static initial condition / OBC params ----
        self.set_output_param("INIT_LAYERS_FROM_Z_FILE", "True")
        self.set_output_param("Z_INIT_ALE_REMAPPING", True)
        self.set_output_param("TEMP_SALT_INIT_VERTICAL_REMAP_ONLY", True)
        self.set_output_param("DEPRESS_INITIAL_SURFACE", True)
        self.set_output_param("VELOCITY_CONFIG", "file")
        self.set_output_param("TEMP_SALT_Z_INIT_FILE", "init_tracers.nc")
        self.set_output_param("SURFACE_HEIGHT_IC_FILE", "init_eta.nc")
        self.set_output_param("VELOCITY_FILE", "init_vel.nc")
        self.set_output_param("Z_INIT_FILE_PTEMP_VAR", "temp")
        self.set_output_param("Z_INIT_FILE_SALT_VAR", "salt")
        self.set_output_param("SURFACE_HEIGHT_IC_VAR", "eta_t")
        self.set_output_param("U_IC_VAR", "u")
        self.set_output_param("V_IC_VAR", "v")

        self.set_output_param("OBC_NUMBER_OF_SEGMENTS", len(boundaries))
        self.set_output_param("OBC_FREESLIP_VORTICITY", "False")
        self.set_output_param("OBC_FREESLIP_STRAIN", "False")
        self.set_output_param("OBC_COMPUTED_VORTICITY", "True")
        self.set_output_param("OBC_COMPUTED_STRAIN", "True")
        self.set_output_param("OBC_ZERO_BIHARMONIC", "True")
        self.set_output_param("OBC_TRACER_RESERVOIR_LENGTH_SCALE_OUT", "3.0E+04")
        self.set_output_param("OBC_TRACER_RESERVOIR_LENGTH_SCALE_IN", "3000.0")
        self.set_output_param("BRUSHCUTTER_MODE", "True")

        # ---- dynamic, per-boundary OBC params ----
        dynamic_params = []
        for seg in boundaries:
            seg_ix = str(self._segment_index(boundaries, seg)).zfill(3)
            seg_id = "OBC_SEGMENT_" + seg_ix

            if seg == "south":
                index_str = '"J=0,I=0:N'
            elif seg == "north":
                index_str = '"J=N,I=N:0'
            elif seg == "west":
                index_str = '"I=0,J=N:0'
            elif seg == "east":
                index_str = '"I=N,J=0:N'
            else:
                raise ValueError(f"Unknown segment {seg_id}")

            position_param = UserNLConfigParam(
                seg_id, comment="Open boundary conditions"
            )
            position_param.set_item(
                index_str + ',FLATHER,ORLANSKI,NUDGED,ORLANSKI_TAN,NUDGED_TAN"'
            )
            dynamic_params.append(position_param)

            nudging_param = UserNLConfigParam(
                seg_id + "_VELOCITY_NUDGING_TIMESCALES",
                comment="Open boundary conditions",
            )
            nudging_param.set_item("0.3, 360.0")
            dynamic_params.append(nudging_param)

            standard_data_str = (
                f'"U=file:forcing_obc_segment_{seg_ix}.nc(u),'
                f"V=file:forcing_obc_segment_{seg_ix}.nc(v),"
                f"SSH=file:forcing_obc_segment_{seg_ix}.nc(eta),"
                f"TEMP=file:forcing_obc_segment_{seg_ix}.nc(temp),"
                f"SALT=file:forcing_obc_segment_{seg_ix}.nc(salt)"
            )

            data_str = standard_data_str
            if self.registry and self.registry.is_active("tides"):
                data_str += (
                    f",Uamp=file:tu_segment_{seg_ix}.nc(uamp),"
                    f"Uphase=file:tu_segment_{seg_ix}.nc(uphase),"
                    f"Vamp=file:tu_segment_{seg_ix}.nc(vamp),"
                    f"Vphase=file:tu_segment_{seg_ix}.nc(vphase),"
                    f"SSHamp=file:tz_segment_{seg_ix}.nc(zamp),"
                    f"SSHphase=file:tz_segment_{seg_ix}.nc(zphase)"
                )
            data_str += '"'

            data_param = UserNLConfigParam(
                seg_id + "_DATA", comment="Open boundary conditions"
            )
            data_param.set_item(data_str)
            dynamic_params.append(data_param)

        # ---- BGC tracer OBC params ----
        # Each BGC tracer lives in a single {tracer}_obc_segment.nc holding all
        # boundaries, so these are emitted once per tracer, not per segment.
        if self.registry and self.registry.is_active("bgc"):
            for tracer_mom6_name, source_var in product.marbl_var_names.items():
                tracer_param = UserNLConfigParam(
                    f"OBC_DATA_{tracer_mom6_name}",
                    comment="Open boundary conditions",
                )
                tracer_param.set_item(
                    f"{tracer_mom6_name}_obc_segment.nc({source_var})"
                )
                dynamic_params.append(tracer_param)

        self.output_params = self.output_params + dynamic_params

        # ---- apply: batch into exactly 2 append_user_nl calls (preserves today's
        # "Initial conditions" / "Open boundary conditions" banner formatting) ----
        ic_params, obc_params = [], []
        for param in self.output_params:
            if not isinstance(param, UserNLConfigParam):
                continue
            (ic_params if param.name in self._IC_PARAM_NAMES else obc_params).append(
                (param.name, param.value)
            )

        append_user_nl("mom", ic_params, do_exec=True, comment="Initial conditions")
        append_user_nl(
            "mom",
            obc_params,
            do_exec=True,
            comment="Open boundary conditions",
            log_title=False,
        )
        for param in self.output_params:
            if isinstance(param, UserNLConfigParam):
                param.executed = True

    @classmethod
    def deserialize(cls, data):
        """Reconstruct dynamic per-boundary output params alongside the static ones."""
        obj = super().deserialize(data)
        boundaries = obj.get_input_param("boundaries")
        for seg in boundaries:
            seg_ix = str(cls._segment_index(boundaries, seg)).zfill(3)
            for suffix in ("", "_VELOCITY_NUDGING_TIMESCALES", "_DATA"):
                name = f"OBC_SEGMENT_{seg_ix}{suffix}"
                if name in data["outputs"]:
                    param = UserNLConfigParam(name, comment="Open boundary conditions")
                    param.set_item(data["outputs"][name])
                    obj.output_params.append(param)
        # BGC tracer params are keyed by tracer, not by segment, and are only
        # present when the bgc configurator was active. Recover them by name so
        # a round-trip preserves them without needing the registry or product.
        existing = {param.name for param in obj.output_params}
        for name, value in data["outputs"].items():
            if name.startswith("OBC_DATA_") and name not in existing:
                param = UserNLConfigParam(name, comment="Open boundary conditions")
                param.set_item(value)
                obj.output_params.append(param)
        return obj

    # ---- process (extraction) ----

    def process_bc(self, ctx):
        """Process MOM6 boundary conditions through forcing.obc's GET → REGRID →
        MERGE engine, using regional_mom6's Segment as the regrid step."""
        product_info = self.get_output_param("information")
        function_args = self.get_output_param("function_args") or {}
        preview = ctx.preview

        if preview:
            return obc.process_obc_conditions(
                start_date=self.get_input_param("start_date"),
                end_date=self.get_input_param("end_date"),
                boundary_number_conversion=self.get_output_param(
                    "boundary_number_conversion"
                ),
                product_name=self.get_input_param("product_name").upper(),
                function_name=self.get_input_param("function_name"),
                variables=None,
                extra_args=None,
                dataset_varnames=product_info,
                hgrid_path=ctx.supergrid_path,
                raw_dataset_path=ctx.raw_data_dir,
                regridded_dataset_path=ctx.regridded_data_dir,
                output_path=ctx.output_path,
                regrid_chunk_fn=_regrid_obc_chunk,
                bathymetry_path=ctx.topo_path,
                get_step_days=int(self.get_output_param("get_step_days")),
                regrid_step_days=int(self.get_output_param("regrid_step_days")),
                preview=True,
            )

        variables, extra_args = build_forcing_request(product_info, function_args)

        if product_info.get("boundary_fill_method", "regional_mom6") != "regional_mom6":
            raise ValueError(
                f"fill_method '{product_info['boundary_fill_method']}' is not supported."
            )

        result = obc.process_obc_conditions(
            start_date=self.get_input_param("start_date"),
            end_date=self.get_input_param("end_date"),
            boundary_number_conversion=self.get_output_param(
                "boundary_number_conversion"
            ),
            product_name=self.get_input_param("product_name").upper(),
            function_name=self.get_input_param("function_name"),
            variables=variables,
            extra_args=extra_args,
            dataset_varnames=product_info,
            hgrid_path=ctx.supergrid_path,
            raw_dataset_path=ctx.raw_data_dir,
            regridded_dataset_path=ctx.regridded_data_dir,
            output_path=ctx.output_path,
            regrid_chunk_fn=_regrid_obc_chunk,
            bathymetry_path=ctx.topo_path,
            get_step_days=int(self.get_output_param("get_step_days")),
            regrid_step_days=int(self.get_output_param("regrid_step_days")),
            preview=False,
        )

        _split_bgc_tracers_into_files(
            output_path=ctx.output_path,
            boundary_number_conversion=self.get_output_param(
                "boundary_number_conversion"
            ),
            marbl_var_names=product_info.get("marbl_var_names", {}),
        )
        return result

    def process_ic(self, ctx):
        """Process the MOM6 initial condition (t=0) through forcing.ic's GET →
        REGRID engine, using regional_mom6's experiment + mom6_forge's fill
        utilities as the regrid step."""
        if not os.path.exists(ctx.vgrid_path):
            raise FileNotFoundError(
                "Vgrid file must exist if run_initial_condition is set to true"
            )

        product_info = self.get_output_param("information")
        function_args = self.get_output_param("function_args") or {}
        preview = ctx.preview
        regrid_fn = partial(
            _regrid_ic,
            hgrid_path=ctx.supergrid_path,
            vgrid_path=ctx.vgrid_path,
            bathymetry_path=ctx.topo_path,
        )

        if preview:
            return ic_mod.process_initial_condition(
                product_name=self.get_input_param("product_name").upper(),
                function_name=self.get_input_param("function_name"),
                variables=None,
                extra_args=None,
                dataset_varnames=product_info,
                start_date=self.get_input_param("start_date"),
                hgrid_path=ctx.supergrid_path,
                raw_data_dir=ctx.raw_data_dir,
                output_data_dir=ctx.output_path,
                regrid_fn=regrid_fn,
                preview=True,
            )

        variables, extra_args = build_forcing_request(product_info, function_args)

        return ic_mod.process_initial_condition(
            product_name=self.get_input_param("product_name").upper(),
            function_name=self.get_input_param("function_name"),
            variables=variables,
            extra_args=extra_args,
            dataset_varnames=product_info,
            start_date=self.get_input_param("start_date"),
            hgrid_path=ctx.supergrid_path,
            raw_data_dir=ctx.raw_data_dir,
            output_data_dir=ctx.output_path,
            regrid_fn=regrid_fn,
            preview=False,
        )
