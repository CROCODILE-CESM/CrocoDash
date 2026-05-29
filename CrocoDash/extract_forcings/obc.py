"""OBC (Open Boundary Condition) forcing extraction for CrocoDash.

Processes boundary conditions through a three-step pipeline:

1. **Get** — download raw data per (boundary, time-chunk) in parallel via Dask.
2. **Regrid** — regrid each chunk to MOM6 segment format. Runs sequentially in
   the main process. xESMF/ESMF cannot initialize its VM in subprocess workers
   on PBS/HPC systems (``ESMCI::VM::getCurrent()`` rc=545), so regridding is
   always serial regardless of whether a Dask client is provided.
3. **Merge** — concatenate all time chunks per boundary into a single
   ``forcing_obc_segment_NNN.nc`` file, in parallel via Dask.

The main entry point is :func:`process_obc_conditions`. Pass a Dask
:class:`~dask.distributed.Client` to parallelize GET and MERGE, or omit it to
run everything sequentially with ``dask.compute``.

Create a client with the helpers in :mod:`CrocoDash.extract_forcings.utils`:

- :func:`~CrocoDash.extract_forcings.utils.make_local_cluster` — local
  multi-process cluster (GET/MERGE only; regrid always runs in main process).
- :func:`~CrocoDash.extract_forcings.utils.make_pbs_cluster` — PBS cluster via
  ``dask-jobqueue``, for HPC batch jobs.
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import dask
import pandas as pd
import regional_mom6 as rm6
import xarray as xr

from CrocoDash import logging
from CrocoDash.extract_forcings import utils
from CrocoDash.extract_forcings.utils import parse_dataset_folder
from CrocoDash.grid import Grid
from CrocoDash.raw_data_access.registry import ProductRegistry

logger = logging.setup_logger(__name__)


def _get_single_chunk(
    boundary: str,
    start_date: datetime,
    end_date: datetime,
    date_format: str,
    hgrid_path,
    output_dir,
    product_name: str,
    function_name: str,
    variables: list,
    extra_args: dict,
) -> Path:
    """Download one (boundary, time_chunk) of raw data."""
    output_dir = Path(output_dir)
    start_str = start_date.strftime(date_format)
    end_str = end_date.strftime(date_format)
    output_file = output_dir / f"{boundary}_unprocessed.{start_str}_{end_str}.nc"

    if output_file.exists():
        try:
            xr.open_dataset(output_file).close()
        except Exception as e:
            raise RuntimeError(
                f"OBC file {output_file} exists but is corrupt: {e}. "
                "Delete it manually and re-run."
            ) from e
        logger.info(f"OBC file {output_file.name} already exists. Skipping download.")
        return output_file

    # Workers run in separate processes -load registry inside each call
    ProductRegistry.load()
    data_access_fn = ProductRegistry.get_access_function(product_name, function_name)

    hgrid = xr.open_dataset(hgrid_path)
    latlon = Grid.get_bounding_boxes_of_rectangular_grid(hgrid)[boundary]

    # copernicusmarine opens S3-backed zarr and calls dask.compute() internally
    # during to_netcdf(). Without this, that compute() routes to the distributed
    # scheduler, which tries to serialize botocore.client.S3 across processes and
    # fails. synchronous keeps it in-process. The outer parallelism (one worker
    # per boundary/chunk) is unaffected.
    with dask.config.set(scheduler="synchronous"):
        data_access_fn(
            dates=[start_str, end_str],
            lat_min=latlon["lat_min"],
            lat_max=latlon["lat_max"],
            lon_min=latlon["lon_min"],
            lon_max=latlon["lon_max"],
            output_folder=output_dir,
            output_filename=output_file.name,
            variables=variables,
            **extra_args,
        )
    return output_file


def _regrid_single_chunk(
    boundary: str,
    seg_id: int,
    file_start: datetime,
    file_end: datetime,
    date_format: str,
    raw_file_path,
    hgrid_path,
    output_folder,
    dataset_varnames: dict,
    fill_method,
    regridders=None,
) -> Path:
    """Regrid one (boundary, time_chunk) raw file. Always called from the main process."""
    output_folder = Path(output_folder)
    start_str = file_start.strftime(date_format)
    end_str = file_end.strftime(date_format)
    dated_output = (
        output_folder / f"forcing_obc_segment_{seg_id:03d}_{start_str}_{end_str}.nc"
    )

    if dated_output.exists():
        logger.info(f"Output file {dated_output.name} already exists. Skipping.")
        return dated_output, None

    (output_folder / "weights").mkdir(exist_ok=True)

    hgrid = xr.open_dataset(hgrid_path)
    seg = rm6.segment(
        hgrid=hgrid,
        bathymetry_path=None,
        outfolder=output_folder,
        segment_name=f"segment_{seg_id:03d}",
        orientation=boundary,
        startdate=file_start,
        repeat_year_forcing=False,
    )

    kwargs = {}
    if "calendar" in dataset_varnames:
        kwargs["calendar"] = dataset_varnames["calendar"]
        kwargs["time_units"] = dataset_varnames["time_units"]

    seg.regrid_velocity_tracers(
        infile=Path(raw_file_path),
        varnames=dataset_varnames,
        arakawa_grid=None,
        rotational_method=rm6.regional_mom6.RotationMethod.EXPAND_GRID,
        regridding_method="bilinear",
        fill_method=fill_method,
        regridders=regridders,
        **kwargs,
    )

    # rm6.segment writes to forcing_obc_segment_{seg_id:03d}.nc -rename to dated version
    temp_path = output_folder / f"forcing_obc_segment_{seg_id:03d}.nc"
    os.rename(temp_path, dated_output)
    logger.info(f"Saved regridded file as {dated_output.name}")
    return dated_output, seg.regridders


def _merge_single_boundary(
    boundary_label: str,
    regridded_file_paths: list,
    output_folder,
) -> Path:
    """Merge all time chunks for one boundary into a single forcing file."""
    output_folder = Path(output_folder)
    output_path = output_folder / f"forcing_obc_segment_{boundary_label}.nc"

    ds = xr.open_mfdataset(
        [str(p) for p in regridded_file_paths],
        combine="nested",
        concat_dim="time",
        coords="minimal",
    )
    ds.to_netcdf(output_path)
    ds.close()
    logger.info(f"Saved merged boundary at {output_path}")
    return output_path


def _log_phase1_graph(
    boundaries, bnc, date_pairs, date_format, get_tasks, regrid_tasks
):
    """Log a summary of the Phase 1 task graph."""
    logger.info(
        "Phase 1 task graph  (%d boundary(ies), %d chunk(s))",
        len(boundaries),
        len(date_pairs),
    )
    for boundary in boundaries:
        seg_label = f"{bnc[boundary]:03d}"
        for i, (start, end) in enumerate(date_pairs):
            has_get = (boundary, i) in get_tasks
            has_regrid = (boundary, i) in regrid_tasks
            steps = []
            if has_get:
                steps.append("get")
            if has_regrid:
                steps.append("regrid (writes weights)" if i == 0 else "regrid")
            if not steps:
                steps.append("skipped")
            date_range = f"{start.strftime(date_format)} -> {end.strftime(date_format)}"
            logger.info(
                "  %s (seg %s) chunk %d  [%s]  %s",
                boundary,
                seg_label,
                i,
                date_range,
                " -> ".join(steps),
            )


def process_obc_conditions(
    config_path,
    skip_get: bool = False,
    skip_regrid: bool = False,
    skip_merge: bool = False,
    client=None,
    preview: bool = False,
    visualize: bool = True,
):
    """
    Process boundary conditions through the three-step pipeline.

    Execution model:

    Phase 1a — GET (parallel via Dask):
      Download one raw file per (boundary, time-chunk) pair. All GET tasks
      are fully independent and run in parallel. Blocks until all downloads
      are complete before proceeding.

    Phase 1b — REGRID (sequential in main process):
      Convert each raw file to MOM6 segment format. Always runs in the calling
      process — one chunk at a time, in boundary/chunk order. xESMF/ESMF cannot
      initialize its VM in subprocess workers on PBS/HPC systems
      (``ESMCI::VM::getCurrent()`` rc=545), so regridding is always serial
      regardless of whether a Dask client is provided.

    Phase 2 — MERGE (parallel via Dask):
      One task per boundary concatenates all time-chunk files into a single
      final forcing file. All merge tasks are independent and run in parallel.
      Starts only after Phase 1 is fully complete.

    Args:
        config_path: Path to the config JSON file.
        skip_get: Skip download; use existing raw files on disk.
        skip_regrid: Skip regridding; use existing regridded files on disk.
        skip_merge: Skip the merge step.
        client: Dask distributed Client. Falls back to ``dask.compute``
                (sequential) if None. Create one with
                :func:`~CrocoDash.extract_forcings.utils.make_local_cluster`
                or :func:`~CrocoDash.extract_forcings.utils.make_pbs_cluster`.
        preview: Return a dict describing what would run, without executing.
        visualize: Save task graph PNGs (phase1_graph.png, phase2_graph.png).
                   Requires graphviz. Disabled by default.
    """
    config = utils.Config(config_path)

    date_format = config["basic"]["dates"]["format"]
    start_date_str = config["basic"]["dates"]["start"]
    end_date_str = config["basic"]["dates"]["end"]
    step_days = int(config["basic"]["general"]["step"])
    bnc = config["basic"]["general"]["boundary_number_conversion"]
    product_name = config["basic"]["forcing"]["product_name"]
    function_name = config["basic"]["forcing"]["function_name"]
    product_info = config["basic"]["forcing"]["information"]
    raw_path = Path(config["basic"]["paths"]["raw_dataset_path"])
    regridded_path = Path(config["basic"]["paths"]["regridded_dataset_path"])
    output_path = Path(config["basic"]["paths"]["output_path"])
    hgrid_path = config["basic"]["paths"]["hgrid_path"]

    dates = (
        pd.date_range(start=start_date_str, end=end_date_str, freq=f"{step_days}D")
        .to_pydatetime()
        .tolist()
    )
    if dates[-1] != datetime.strptime(end_date_str, date_format):
        dates.append(datetime.strptime(end_date_str, date_format))

    # Build non-overlapping pairs: end of one chunk + 1 day = start of next
    date_pairs = []
    chunk_start = dates[0]
    for i in range(len(dates) - 1):
        chunk_end = dates[i + 1]
        date_pairs.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    boundaries = list(bnc.keys())

    logger.info(
        f"Step size {step_days} days -> {len(date_pairs)} chunk(s) x {len(boundaries)} boundary(ies)."
    )

    start_dt = datetime.strptime(start_date_str, date_format)
    end_dt = datetime.strptime(end_date_str, date_format)

    # -------------------------------------------------------------------------
    # Compute all expected file paths upfront.
    #
    # Preview uses these directly. The execution path reuses them, so we scan
    # each directory at most once regardless of whether preview is enabled.
    # -------------------------------------------------------------------------

    # Expected output path for each (boundary, chunk) get task
    get_outputs = {
        (boundary, i): raw_path
        / f"{boundary}_unprocessed.{start.strftime(date_format)}_{end.strftime(date_format)}.nc"
        for boundary in boundaries
        for i, (start, end) in enumerate(date_pairs)
    }

    # Raw inputs consumed by regrid: scan disk if get was skipped, otherwise
    # the expected get outputs are what regrid will read
    raw_inputs = {}
    if skip_get:
        raw_regex = config["basic"]["file_regex"]["raw_dataset_pattern"]
        raw_file_list = parse_dataset_folder(raw_path, raw_regex, date_format)
        for boundary in boundaries:
            idx = 0
            for fs, fe, fp in sorted(raw_file_list.get(boundary, [])):
                if fs <= end_dt and fe >= start_dt:
                    raw_inputs[(boundary, idx)] = Path(fp)
                    idx += 1
    else:
        raw_inputs = dict(get_outputs)

    # Expected output path for each (boundary, chunk) regrid task
    regrid_outputs = {
        (boundary, i): regridded_path
        / f"forcing_obc_segment_{bnc[boundary]:03d}_{start.strftime(date_format)}_{end.strftime(date_format)}.nc"
        for boundary in boundaries
        for i, (start, end) in enumerate(date_pairs)
        if (boundary, i) in raw_inputs
    }

    # Regridded inputs consumed by merge: scan disk if regrid was skipped,
    # otherwise derive from the expected regrid output paths
    regridded_inputs = defaultdict(list)
    if skip_regrid:
        regridded_regex = config["basic"]["file_regex"]["regridded_dataset_pattern"]
        regridded_file_list = parse_dataset_folder(
            regridded_path, regridded_regex, date_format
        )
        for boundary, seg_id in bnc.items():
            seg_label = f"{seg_id:03d}"
            for fs, fe, fp in sorted(regridded_file_list.get(seg_label, [])):
                if fs <= end_dt and fe >= start_dt:
                    regridded_inputs[seg_label].append(Path(fp))
    else:
        for (boundary, i), path in regrid_outputs.items():
            regridded_inputs[f"{bnc[boundary]:03d}"].append(path)
        for seg_label in regridded_inputs:
            regridded_inputs[seg_label].sort()

    # Expected merge output for each boundary segment
    merge_outputs = {
        seg_label: output_path / f"forcing_obc_segment_{seg_label}.nc"
        for seg_label in regridded_inputs
    }

    # -------------------------------------------------------------------------
    # Preview: return the computed metadata without running any expensive tasks.
    # -------------------------------------------------------------------------
    if preview:
        return {
            "date_pairs": date_pairs,
            "get_outputs": get_outputs,
            "raw_inputs": raw_inputs,
            "regrid_outputs": regrid_outputs,
            "regridded_inputs": dict(regridded_inputs),
            "merge_outputs": merge_outputs,
        }

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
        k: product_info[k]
        for k in ("dataset_path", "date_format", "regex", "delimiter")
        if k in product_info
    }

    fill_method = rm6.regridding.fill_missing_data
    if product_info.get("boundary_fill_method", "regional_mom6") != "regional_mom6":
        raise ValueError(
            f"fill_method '{product_info['boundary_fill_method']}' is not supported."
        )

    raw_path.mkdir(exist_ok=True)
    regridded_path.mkdir(exist_ok=True)
    output_path.mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # Phase 1a task graph: Get
    #
    # GET tasks are fully independent across all (boundary, chunk) pairs and
    # run in parallel via Dask workers.
    # -------------------------------------------------------------------------

    # get_tasks[(boundary, chunk_index)] = delayed call to _get_single_chunk
    get_tasks = {}
    if not skip_get:
        for boundary in boundaries:
            for i, (start, end) in enumerate(date_pairs):
                get_tasks[(boundary, i)] = dask.delayed(_get_single_chunk)(
                    boundary=boundary,
                    start_date=start,
                    end_date=end,
                    date_format=date_format,
                    hgrid_path=str(hgrid_path),
                    output_dir=str(raw_path),
                    product_name=product_name,
                    function_name=function_name,
                    variables=variables,
                    extra_args=extra_args,
                )

    # regrid_tasks is a plain dict used only for logging — regridding runs
    # sequentially in the main process (see Phase 1b below).
    regrid_tasks = {}
    if not skip_regrid:
        for boundary in boundaries:
            for i in range(len(date_pairs)):
                if raw_inputs.get((boundary, i)) is not None:
                    regrid_tasks[(boundary, i)] = True

    _log_phase1_graph(boundaries, bnc, date_pairs, date_format, get_tasks, regrid_tasks)

    # Execute Phase 1a: GET in parallel.
    if not skip_get and get_tasks:
        if visualize:
            dask.visualize(*get_tasks.values(), filename="phase1_get_graph.png")
            logger.info("Task graph image saved to phase1_get_graph.png")
        if client is not None:
            futures = client.compute(list(get_tasks.values()))
            client.gather(futures)
        else:
            dask.compute(*get_tasks.values())

    # -------------------------------------------------------------------------
    # Phase 1b: Regrid sequentially in the main process.
    #
    # xESMF/ESMF cannot initialize its VM (parallel environment) in subprocess
    # workers on PBS/HPC systems — ESMCI::VM::getCurrent() returns
    # "Could not determine current VM" (rc=545) in any child process.
    # Running regridding in the main process avoids this entirely.
    #
    # raw_inputs paths are deterministic (derived from config dates/boundary
    # names), so regrid can read them directly after GET has written them.
    # -------------------------------------------------------------------------

    if not skip_regrid:
        logger.info("Regridding sequentially in main process...")
        for boundary in boundaries:
            seg_id = bnc[boundary]
            regridders = None
            for i, (start, end) in enumerate(date_pairs):
                raw_arg = raw_inputs.get((boundary, i))
                if raw_arg is None:
                    logger.warning(
                        "No raw file for %s chunk %d, skipping regrid.", boundary, i
                    )
                    continue

                dated_ouput, regridders = _regrid_single_chunk(
                    boundary=boundary,
                    seg_id=seg_id,
                    file_start=start,
                    file_end=end,
                    date_format=date_format,
                    raw_file_path=raw_arg,
                    hgrid_path=str(hgrid_path),
                    output_folder=str(regridded_path),
                    dataset_varnames=product_info,
                    fill_method=fill_method,
                    regridders=regridders,
                )

    if skip_merge:
        return

    # -------------------------------------------------------------------------
    # Phase 2 task graph: Merge
    #
    # One merge task per boundary. Each merge task receives the list of all
    # regridded chunk files for that boundary and concatenates them along the
    # time dimension into a single final forcing file.
    #
    # All merge tasks are independent of each other and run in parallel.
    # Phase 2 only starts after ALL of Phase 1 is done (we waited above with
    # client.gather / dask.compute before building these tasks).
    # -------------------------------------------------------------------------

    # regridded_inputs was built upfront: either scanned from disk (skip_regrid)
    # or derived from the expected regrid output paths. Both cases are resolved
    # before the preview check, so we reuse the same variable here.
    merge_tasks = [
        dask.delayed(_merge_single_boundary)(
            boundary_label=seg_label,
            regridded_file_paths=paths,
            output_folder=str(output_path),
        )
        for seg_label, paths in regridded_inputs.items()
    ]

    logger.info(
        "Phase 2 task graph  (%d merge task(s), all independent)", len(merge_tasks)
    )
    for seg_label, paths in regridded_inputs.items():
        logger.info(
            "  seg %s: merge %d chunk(s) -> forcing_obc_segment_%s.nc",
            seg_label,
            len(paths),
            seg_label,
        )
    if visualize and merge_tasks:
        dask.visualize(*merge_tasks, filename="phase2_graph.png")
        logger.info("Task graph image saved to phase2_graph.png")

    if merge_tasks:
        if client is not None:
            futures = client.compute(merge_tasks)
            client.gather(futures)
        else:
            dask.compute(*merge_tasks)

    logger.info("OBC processing complete.")
