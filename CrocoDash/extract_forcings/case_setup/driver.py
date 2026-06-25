"""CrocoDash Forcing Extraction Driver

This module orchestrates the forcing extraction workflow for a CrocoDash case.
It coordinates multiple forcing data sources (tides, runoff, BGC, etc.) and processes them
into MOM6-compatible file formats.

The script can be run from the command line with various component flags to control which
forcings are processed. It loads configuration from config.json and coordinates all extraction,
regridding, and formatting operations.

OBC processing (``--bc``) uses Dask for the **GET** (download) step only.
**REGRID** and **MERGE** always run sequentially in the main process — xESMF/ESMF
cannot initialize its parallel environment in subprocess workers on PBS/HPC
systems (see :mod:`CrocoDash.extract_forcings.obc`).

By default everything runs without a cluster (sequential ``dask.compute``). Pass
``--n-workers N`` to launch a ``LocalCluster`` that parallelises GET. For PBS
clusters, add ``--pbs`` along with optional ``--queue``, ``--walltime``,
``--memory``, ``--cores``, and ``--resource-spec`` flags (requires
``dask-jobqueue``). For full Python control (e.g. SLURM), create a client with
:func:`~CrocoDash.extract_forcings.utils.make_pbs_cluster` and pass it to
:func:`run_workflow` directly.

Typical CLI usage::

    python driver.py --all                          # all components, sequential OBC
    python driver.py --bc --n-workers 4             # OBC with 4 local workers
    python driver.py --bc --n-workers 8 --pbs \
        --queue regular --walltime 02:00:00         # OBC with 8 PBS jobs
    python driver.py --bc --n-workers 8 --pbs \
        --queue regular --visualize                 # same, plus Dask dashboard link
    python driver.py --tides --bgcic                # tides and BGC IC only
    python driver.py --all --skip runoff            # all except runoff

Typical Python usage (HPC power users)::

    from CrocoDash.extract_forcings.utils import make_pbs_cluster
    from CrocoDash.extract_forcings.case_setup.driver import run_workflow

    client = make_pbs_cluster(n_workers=8, queue="regular", walltime="02:00:00")
    run_workflow(bc=True, ic=True, client=client, visualize=True)
    client.close()

.. note::

    On HPC systems (PBS/SLURM), the Dask dashboard runs on an internal compute
    node that is not directly reachable from your laptop. When ``--visualize``
    is used with ``--pbs``, the driver prints a ready-to-run SSH tunnel command.
    Run it on your laptop to forward the port, then open ``http://localhost:<port>/status``
    in a browser::

        ssh -L 8787:<compute-node>:8787 <login-node>
"""

import sys
import time
from pathlib import Path
from urllib.parse import urlparse
import argparse

from CrocoDash.extract_forcings import (
    bgc,
    runoff as rof,
    tides,
    chlorophyll as chl,
    utils as utils,
    initial_condition as initial_condition,
)
from CrocoDash.extract_forcings.obc import (
    process_obc_conditions as process_obc,
)

CONFIG_PATH = Path(__file__).parent / "config.json"


def test_driver():
    """Test that all the imports work"""
    print("All Imports Work!")
    config = utils.Config(CONFIG_PATH)
    print("Config Loads!")
    return


def process_bgcic():
    """Extract and copy BGC initial conditions from CESM MARBL inputdata."""
    config = utils.Config(CONFIG_PATH)
    bgc.process_bgc_ic(
        file_path=config["bgcic"]["inputs"]["marbl_ic_filepath"],
        output_path=config.inputdir
        / "ocnice"
        / config["bgcic"]["outputs"]["MARBL_TRACERS_IC_FILE"],
    )


def process_bgcironforcing():
    config = utils.Config(CONFIG_PATH)
    bgc.process_bgc_iron_forcing(
        nx=config.ocn_grid.nx,
        ny=config.ocn_grid.ny,
        MARBL_FESEDFLUX_FILE=config["bgcironforcing"]["outputs"][
            "MARBL_FESEDFLUX_FILE"
        ],
        MARBL_FEVENTFLUX_FILE=config["bgcironforcing"]["outputs"][
            "MARBL_FEVENTFLUX_FILE"
        ],
        inputdir=config.inputdir,
    )


def process_runoff():
    """Generate runoff mapping files and interpolation weights."""
    config = utils.Config(CONFIG_PATH)
    rof.generate_rof_ocn_map(
        rof_grid_name=config["runoff"]["inputs"]["rof_grid_name"],
        rof_esmf_mesh_filepath=config["runoff"]["inputs"]["rof_esmf_mesh_filepath"],
        ocn_mesh_filepath=config["runoff"]["inputs"]["case_esmf_mesh_path"],
        inputdir=config.inputdir,
        grid_name=config["runoff"]["inputs"]["case_grid_name"],
        rmax=config["runoff"]["inputs"]["rmax"],
        fold=config["runoff"]["inputs"]["fold"],
    )


def process_bgcrivernutrients():
    """Process river nutrient inputs for BGC."""
    config = utils.Config(CONFIG_PATH)
    bgc.process_river_nutrients(
        ocn_grid=config.ocn_grid,
        global_river_nutrients_filepath=config["bgcrivernutrients"]["inputs"][
            "global_river_nutrients_filepath"
        ],
        mapping_file=config["runoff"]["outputs"]["ROF2OCN_LIQ_RMAPNAME"],
        river_nutrients_nnsm_filepath=config.inputdir
        / "ocnice"
        / config["bgcrivernutrients"]["outputs"]["RIV_FLUX_FILE"],
    )


def process_tides():
    """Extract and process tidal forcing from TPXO database."""
    config = utils.Config(CONFIG_PATH)
    tides.process_tides(
        ocn_topo=config.ocn_topo,
        inputdir=config.inputdir,
        supergrid_path=config["basic"]["paths"]["hgrid_path"],
        vgrid_path=config["basic"]["paths"]["vgrid_path"],
        tidal_constituents=config["tides"]["inputs"]["tidal_constituents"],
        boundaries=config["tides"]["inputs"]["boundaries"],
        tpxo_elevation_filepath=config["tides"]["inputs"]["tpxo_elevation_filepath"],
        tpxo_velocity_filepath=config["tides"]["inputs"]["tpxo_velocity_filepath"],
    )


def process_chl():
    """Process satellite-derived chlorophyll data"""
    config = utils.Config(CONFIG_PATH)
    chl.process_chl(
        ocn_grid=config.ocn_grid,
        ocn_topo=config.ocn_topo,
        inputdir=config.inputdir,
        chl_processed_filepath=config["chl"]["inputs"]["chl_processed_filepath"],
        output_filepath=config["chl"]["outputs"]["CHL_FILE"],
    )


def should_run(name, args, cfg):
    not_skipped = name.lower() not in args.skip
    requested = args.all or getattr(args, name)
    exists = name in cfg.config.keys()

    if requested and not exists:
        print(f"[skip] '{name}' requested but not in config")

    if requested and not not_skipped:
        print(f"[skip] '{name}' skipped via --skip")

    return requested and exists and not_skipped


def parse_args():
    parser = argparse.ArgumentParser(description="CrocoDash forcing workflow driver")

    top = parser.add_argument_group("Top-level actions")
    top.add_argument("--all", action="store_true", help="Run all components")
    top.add_argument("--test", action="store_true", help="Run import/config test only")

    components = parser.add_argument_group("Forcing components")
    components.add_argument("--ic", action="store_true", help="Run initial conditions")
    components.add_argument("--bc", action="store_true", help="Run boundary conditions")
    components.add_argument(
        "--bgcic", action="store_true", help="Run BGC initial conditions"
    )
    components.add_argument(
        "--bgcironforcing", action="store_true", help="Run BGC iron forcing"
    )
    components.add_argument(
        "--bgcrivernutrients",
        action="store_true",
        help="Run BGC river nutrients (requires runoff)",
    )
    components.add_argument(
        "--runoff", action="store_true", help="Run runoff mapping and interpolation"
    )
    components.add_argument(
        "--tides", action="store_true", help="Run tidal forcing from TPXO"
    )
    components.add_argument(
        "--chl", action="store_true", help="Run chlorophyll processing"
    )

    top.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Skip components by name (e.g. --skip tides runoff)",
    )

    cluster_opts = parser.add_argument_group(
        "Cluster options",
        "Parallelise OBC GET (download) step. REGRID and MERGE always run "
        "sequentially in the main process. Omit --n-workers to skip cluster "
        "setup entirely.",
    )
    cluster_opts.add_argument(
        "--n-workers",
        type=int,
        default=None,
        help="Number of workers. With --pbs, submits N PBS jobs; otherwise starts a LocalCluster.",
    )
    cluster_opts.add_argument(
        "--pbs",
        action="store_true",
        help="Use a PBS cluster instead of a local cluster (requires dask-jobqueue).",
    )
    cluster_opts.add_argument(
        "--queue",
        default=None,
        help="PBS queue/partition (e.g. 'regular'). Site-specific.",
    )
    cluster_opts.add_argument(
        "--walltime",
        default="01:00:00",
        help="Walltime per PBS job (default: 01:00:00).",
    )
    cluster_opts.add_argument(
        "--memory",
        default="4GiB",
        help="Memory per PBS job (default: 4GiB).",
    )
    cluster_opts.add_argument(
        "--cores",
        type=int,
        default=1,
        help="CPU cores per PBS job (default: 1).",
    )
    cluster_opts.add_argument(
        "--resource-spec",
        default=None,
        help="Raw PBS -l resource string (e.g. 'select=1:ncpus=4:mem=4gb'). Overrides --cores/--memory.",
    )
    cluster_opts.add_argument(
        "--visualize",
        action="store_true",
        help="Print the Dask dashboard link when a cluster is active (requires --n-workers or --pbs).",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    return parser.parse_args()


def resolve_components(args, cfg):
    """
    Resolve which components should run based on CLI flags and config availability.

    This function takes the parsed command-line arguments and the configuration, then
    determines which forcing components should actually execute. It handles:
    - --all: Enable all components that exist in config
    - --skip: Disable specific components by name (case-insensitive)
    - Individual flags: Enable only specified components
    - Config validation: Skip components requested but not in config

    The function modifies args in-place, setting each component flag to True/False
    based on the resolution logic.

    Args:
        args: Parsed command-line arguments (from parse_args())
        cfg: Config object with .config dict of available components

    Returns:
        Modified args object with all component flags resolved
    """
    components = {
        k: v
        for k, v in vars(args).items()
        if isinstance(v, bool)
        and k
        not in {
            "all",
            "test",
            "pbs",
            "visualize",
        }
    }

    skip = {s.lower() for s in args.skip}

    for name in components:
        requested = args.all or getattr(args, name)
        if name != "ic" and name != "bc":
            exists = name in cfg.config
        else:
            exists = True

        should_run = requested and exists and name not in skip

        if requested and not exists:
            print(f"[skip] '{name}' requested but not in config")
        elif requested and name in skip:
            print(f"[skip] '{name}' skipped via --skip")

        # overwrite args.<component>
        setattr(args, name, should_run)

    return args


def run_workflow(
    ic=False,
    bc=False,
    bgcic=False,
    bgcironforcing=False,
    tides=False,
    chl=False,
    runoff=False,
    bgcrivernutrients=False,
    preview=False,
    cfg=None,
    client=None,
    n_workers=None,
    visualize=False,
    pbs=False,
):
    """
    Execute the forcing extraction workflow.

    This is the shared core used by both run_from_cli and case.py's process_forcings.
    Each boolean flag enables the corresponding component. Components run sequentially;
    parallelism is handled internally by individual components (e.g., OBC uses Dask).

    Args:
        ic:                  Run initial conditions
        bc:                  Run boundary conditions (OBC; parallel internally via Dask)
        bgcic:               Run BGC initial conditions
        bgcironforcing:      Run BGC iron forcing
        tides:               Run tidal forcing
        chl:                 Run chlorophyll processing
        runoff:              Run runoff mapping
        bgcrivernutrients:   Run BGC river nutrients (always runs after runoff)
        preview:             Preview task graph without executing
        cfg:                 Config object; loaded from CONFIG_PATH if None
        client:              Dask distributed Client (power users). Caller owns lifecycle.
                             Create one with :func:`~CrocoDash.extract_forcings.utils.make_pbs_cluster`
                             or :func:`~CrocoDash.extract_forcings.utils.make_local_cluster`.
        n_workers:           Spin up a LocalCluster with this many workers for GET.
                             REGRID and MERGE always run sequentially in the main
                             process. Ignored if client is already provided. If neither
                             is set, OBC uses ``dask.compute`` with no cluster overhead.
        visualize:           If True and a Dask client is active, print the Dask
                             dashboard link so progress can be monitored in a browser.
                             When ``pbs=True``, also prints a ready-to-run SSH tunnel
                             command for reaching the dashboard from outside the cluster.
        pbs:                 Set to True when the client was created with a PBS cluster.
                             Only affects the extra SSH hint printed by ``visualize``.
    """
    if cfg is None:
        cfg = utils.Config(CONFIG_PATH)

    if not any([ic, bc, bgcic, bgcironforcing, tides, chl, runoff, bgcrivernutrients]):
        print("No components selected.")
        return

    own_client = client is None and n_workers is not None
    if own_client:
        client = utils.make_local_cluster(n_workers=n_workers)

    if visualize:
        if client is not None:
            print(f"[dask] Dashboard: {client.dashboard_link}")
            if pbs:
                parsed = urlparse(client.dashboard_link)
                host = parsed.hostname or "<compute-node>"
                port = parsed.port or 8787
                print(
                    f"[dask] PBS/HPC tunnel (run on your laptop): "
                    f"ssh -L {port}:{host}:{port} <login-node>"
                )
                print(f"[dask]   then open: http://localhost:{port}/status")
        else:
            print(
                "[dask] --visualize requested but no Dask client is active "
                "(pass --n-workers or --pbs to enable a cluster)."
            )

    timings = {}
    try:
        if bc:
            _t = time.perf_counter()
            process_obc(
                config_path=CONFIG_PATH,
                client=client,
                preview=preview,
            )
            timings["bc"] = time.perf_counter() - _t

        if ic:
            _t = time.perf_counter()
            initial_condition.process_initial_condition(
                product_name=cfg["basic"]["forcing"]["product_name"],
                function_name=cfg["basic"]["forcing"]["function_name"],
                product_information=cfg["basic"]["forcing"]["information"],
                date_format=cfg["basic"]["dates"]["format"],
                start_date=cfg["basic"]["dates"]["start"],
                hgrid_path=cfg["basic"]["paths"]["hgrid_path"],
                vgrid_path=cfg["basic"]["paths"]["vgrid_path"],
                dataset_varnames=cfg["basic"]["forcing"]["information"],
                raw_data_dir=cfg["basic"]["paths"]["raw_dataset_path"],
                output_data_dir=cfg["basic"]["paths"]["output_path"],
                bathymetry_path=cfg["basic"]["paths"]["bathymetry_path"],
                preview=preview,
            )
            timings["ic"] = time.perf_counter() - _t

        if bgcic:
            _t = time.perf_counter()
            process_bgcic()
            timings["bgcic"] = time.perf_counter() - _t

        if bgcironforcing:
            _t = time.perf_counter()
            process_bgcironforcing()
            timings["bgcironforcing"] = time.perf_counter() - _t

        if tides:
            _t = time.perf_counter()
            process_tides()
            timings["tides"] = time.perf_counter() - _t

        if chl:
            _t = time.perf_counter()
            process_chl()
            timings["chl"] = time.perf_counter() - _t

        if runoff:
            _t = time.perf_counter()
            process_runoff()
            timings["runoff"] = time.perf_counter() - _t

        if bgcrivernutrients:
            _t = time.perf_counter()
            process_bgcrivernutrients()
            timings["bgcrivernutrients"] = time.perf_counter() - _t
    finally:
        if own_client:
            client.close()

    if timings:
        parts = [f"{k}: {v:.1f}s" for k, v in timings.items()]
        parts.append(f"total: {sum(timings.values()):.1f}s")
        print("[timing] " + "  ".join(parts))

    return timings


def run_from_cli(args, cfg):
    """
    Execute the forcing extraction workflow based on CLI arguments.

    Args:
        args: Parsed and resolved command-line arguments
        cfg: Config object from utils.Config(CONFIG_PATH)
    """
    if args.test:
        test_driver()
        return

    if args.pbs and args.n_workers is None:
        raise ValueError("--pbs requires --n-workers")

    args = resolve_components(args, cfg)

    client = None
    if args.pbs:
        client = utils.make_pbs_cluster(
            n_workers=args.n_workers,
            cores=args.cores,
            memory=args.memory,
            walltime=args.walltime,
            queue=args.queue,
            resource_spec=args.resource_spec,
        )

    workflow_kwargs = dict(
        ic=args.ic,
        bc=args.bc,
        bgcic=args.bgcic,
        bgcironforcing=args.bgcironforcing,
        tides=args.tides,
        chl=args.chl,
        runoff=args.runoff,
        bgcrivernutrients=args.bgcrivernutrients,
        preview=cfg["basic"]["general"].get("preview", False),
        cfg=cfg,
        client=client,
        n_workers=args.n_workers if not args.pbs else None,
        visualize=args.visualize,
        pbs=args.pbs,
    )

    try:
        run_workflow(**workflow_kwargs)
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    args = parse_args()
    cfg = utils.Config(CONFIG_PATH)
    run_from_cli(args, cfg)
