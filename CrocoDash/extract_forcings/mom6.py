"""MOM6-specific OBC/IC handling for CrocoDash.

``obc.py``/``ic.py`` are model-agnostic engines: they get raw data (and, for
OBC, date-chunk/merge it) but know nothing about how to regrid it onto a
target model's grid. This module supplies MOM6's own regrid step -- built on
``regional_mom6``'s ``segment``/``experiment`` classes and ``mom6_forge``'s
fill utilities -- and the MOM6-specific piece of the GET step (turning a
forcing product's own u/v/eta/tracer var-name metadata into a download
request). ``process_mom6_obc``/``process_mom6_ic`` are the entry points
``driver.py`` calls; they have the same external shape as the old
``obc.process_obc_conditions``/``ic.process_initial_condition`` did before
those were generalized.
"""

import os
from functools import partial
from pathlib import Path

import dask
import netCDF4
import regional_mom6 as rm6
import mom6_forge as m6b
import xarray as xr
from CrocoDash import logging
from CrocoDash.extract_forcings import obc, ic as ic_mod, utils
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo

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
# OBC
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
    kwargs = {}
    if "calendar" in dataset_varnames:
        kwargs["calendar"] = dataset_varnames["calendar"]
        kwargs["time_units"] = dataset_varnames["time_units"]

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
            calendar=dataset_varnames["mom6_calendar"],
            time_units=dataset_varnames["time_units"],
            # Opt in to ESMF skipping degenerate (duplicate/collapsed) source
            # cells rather than aborting the regrid with "rc=506 (Degenerate
            # Element Detected)". Global products have them near the poles --
            # GLORYS at its southernmost latitudes -- so polar domains fail
            # outright without this. rm6 defaults it off so a source grid that
            # is malformed for some other reason still fails loudly.
            ignore_degenerate=True,
            **kwargs,
        )
        return seg.regridders
    finally:
        tmp_file.unlink(missing_ok=True)


def _split_bgc_tracers_into_files(
    output_path, boundary_number_conversion: dict, marbl_var_names: dict
):
    """Copy each BGC tracer out of the per-boundary OBC files into its own file.

    MOM6's generic tracer code reads BGC open-boundary data from one file per
    tracer holding every segment (``<tracer>_obc_segment.nc``), whereas the
    physical tracers are read per boundary from
    ``forcing_obc_segment_NNN.nc``. The regrid step writes the BGC tracers into
    those per-boundary files alongside temp/salt, so without this step the
    per-tracer files MOM6 is pointed at never exist.

    Mirrors regional_mom6's ``reformat_bgc_tracers_into_files``, which only runs
    inside rm6's own ``setup_ocean_state_boundaries`` and so is never reached by
    this pipeline.
    """
    if not marbl_var_names:
        return []

    output_path = Path(output_path)
    seg_ids = [f"{n:03d}" for n in boundary_number_conversion.values()]
    written = []

    for var in marbl_var_names:
        ds_var = xr.Dataset()
        for seg in seg_ids:
            seg_file = output_path / f"forcing_obc_segment_{seg}.nc"
            with xr.open_dataset(seg_file) as ds:
                var_name = f"{var}_segment_{seg}"
                if var_name not in ds:
                    raise KeyError(
                        f"BGC tracer variable {var_name!r} not found in "
                        f"{seg_file}. Expected it there because {var!r} was "
                        "included in the regridded tracer set."
                    )
                # .load() because the source file is closed on leaving this block.
                ds_var[var_name] = ds[var_name].load()
                dz_var_name = f"dz_{var_name}"
                if dz_var_name in ds:
                    ds_var[dz_var_name] = ds[dz_var_name].load()

        out_file = output_path / f"{var}_obc_segment.nc"
        ds_var.to_netcdf(out_file, unlimited_dims="time")
        written.append(out_file)
        logger.info("BGC SPLIT: wrote %s", out_file.name)

    return written


def process_mom6_obc(
    start_date,
    end_date,
    boundary_number_conversion: dict,
    product_name: str,
    function_name: str,
    product_info: dict,
    hgrid_path,
    raw_dataset_path,
    regridded_dataset_path,
    output_path,
    get_step_days=None,
    regrid_step_days: int = 30,
    function_args: dict = None,
    bathymetry_path=None,
    preview: bool = False,
):
    """Process MOM6 boundary conditions through obc.py's GET → REGRID → MERGE
    engine, using regional_mom6's Segment as the regrid step.

    Args mirror obc.process_obc_conditions's pre-generalization signature --
    see that function's docstring for the shared-engine parameters, and
    build_forcing_request/_regrid_obc_chunk above for what's MOM6-specific.
    """
    if preview:
        return obc.process_obc_conditions(
            start_date=start_date,
            end_date=end_date,
            boundary_number_conversion=boundary_number_conversion,
            product_name=product_name,
            function_name=function_name,
            variables=None,
            extra_args=None,
            dataset_varnames=product_info,
            hgrid_path=hgrid_path,
            raw_dataset_path=raw_dataset_path,
            regridded_dataset_path=regridded_dataset_path,
            output_path=output_path,
            regrid_chunk_fn=_regrid_obc_chunk,
            get_step_days=get_step_days,
            regrid_step_days=regrid_step_days,
            bathymetry_path=bathymetry_path,
            preview=True,
        )

    variables, extra_args = build_forcing_request(product_info, function_args)

    if product_info.get("boundary_fill_method", "regional_mom6") != "regional_mom6":
        raise ValueError(
            f"fill_method '{product_info['boundary_fill_method']}' is not supported."
        )

    result = obc.process_obc_conditions(
        start_date=start_date,
        end_date=end_date,
        boundary_number_conversion=boundary_number_conversion,
        product_name=product_name,
        function_name=function_name,
        variables=variables,
        extra_args=extra_args,
        dataset_varnames=product_info,
        hgrid_path=hgrid_path,
        raw_dataset_path=raw_dataset_path,
        regridded_dataset_path=regridded_dataset_path,
        output_path=output_path,
        regrid_chunk_fn=_regrid_obc_chunk,
        get_step_days=get_step_days,
        regrid_step_days=regrid_step_days,
        bathymetry_path=bathymetry_path,
        preview=False,
    )

    # MOM6-specific, so it lives here rather than in obc.py's generic engine.
    _split_bgc_tracers_into_files(
        output_path=output_path,
        boundary_number_conversion=boundary_number_conversion,
        marbl_var_names=product_info.get("marbl_var_names", {}),
    )

    return result


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------


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
    part of ic.py's generic engine signature -- process_mom6_ic below binds
    them via functools.partial before handing this to the engine as
    regrid_fn."""
    expt = rm6.experiment.create_empty()
    # hgrid/vgrid are now read-only properties derived from m6f_hgrid/
    # m6f_vgrid (mom6_forge Grid/VGrid objects) -- set those instead.
    # _make_vgrid already sets m6f_vgrid as a side effect.
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


def process_mom6_ic(
    product_name: str,
    function_name: str,
    product_information: dict,
    start_date,
    hgrid_path,
    vgrid_path,
    dataset_varnames: dict,
    raw_data_dir,
    output_data_dir,
    bathymetry_path,
    preview: bool = False,
    function_args: dict = None,
):
    """Process the MOM6 initial condition (t=0) through ic.py's GET → REGRID
    engine, using regional_mom6's experiment + mom6_forge's fill utilities as
    the regrid step.

    Args mirror ic.process_initial_condition's pre-generalization signature.
    """
    if not os.path.exists(vgrid_path):
        raise FileNotFoundError(
            "Vgrid file must exist if run_initial_condition is set to true"
        )

    if preview:
        return ic_mod.process_initial_condition(
            product_name=product_name,
            function_name=function_name,
            variables=None,
            extra_args=None,
            dataset_varnames=dataset_varnames,
            start_date=start_date,
            hgrid_path=hgrid_path,
            raw_data_dir=raw_data_dir,
            output_data_dir=output_data_dir,
            regrid_fn=partial(
                _regrid_ic,
                hgrid_path=hgrid_path,
                vgrid_path=vgrid_path,
                bathymetry_path=bathymetry_path,
            ),
            preview=True,
        )

    variables, extra_args = build_forcing_request(product_information, function_args)

    return ic_mod.process_initial_condition(
        product_name=product_name,
        function_name=function_name,
        variables=variables,
        extra_args=extra_args,
        dataset_varnames=dataset_varnames,
        start_date=start_date,
        hgrid_path=hgrid_path,
        raw_data_dir=raw_data_dir,
        output_data_dir=output_data_dir,
        regrid_fn=partial(
            _regrid_ic,
            hgrid_path=hgrid_path,
            vgrid_path=vgrid_path,
            bathymetry_path=bathymetry_path,
        ),
        preview=False,
    )
