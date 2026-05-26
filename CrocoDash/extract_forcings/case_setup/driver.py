"""CrocoDash Forcing Extraction Driver

This module orchestrates the forcing extraction workflow for a CrocoDash case.
It coordinates multiple forcing data sources (tides, runoff, BGC, etc.) and processes them
into MOM6-compatible file formats.

The script can be run from the command line with various component flags to control which
forcings are processed. It loads configuration from config.json and coordinates all extraction,
regridding, and formatting operations.

Typical usage:
    python driver.py --all                  # Process all configured components
    python driver.py --tides --bgcic        # Process only tides and BGC initial conditions
    python driver.py --all --skip runoff    # Process all except runoff
    python driver.py --ic --no-get          # Process IC but skip data download step
"""

import sys
from pathlib import Path
import argparse
import dask
from dask.distributed import as_completed

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


def _after(_, fn):
    """Run fn() after a dependency task completes. The dependency result is ignored."""
    return fn()


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

    conditions_opts = parser.add_argument_group("Conditions options")
    conditions_opts.add_argument("--no-get", action="store_true")
    conditions_opts.add_argument("--no-regrid", action="store_true")
    conditions_opts.add_argument("--no-merge", action="store_true")

    top.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Skip components by name (e.g. --skip tides runoff)",
    )

    parser.add_argument(
        "--scheduler",
        default=None,
        choices=["pbs", "slurm", "lsf", "sge"],
        help="HPC scheduler type. Omit for local/interactive.",
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=1,
        help="Number of dask workers (processes). Increase for more parallelism.",
    )
    parser.add_argument(
        "--threads-per-worker",
        type=int,
        default=1,
        help="Threads per worker. Keep at 1 — xESMF/ESMF is not thread-safe.",
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
        and k not in {"all", "test", "no_get", "no_regrid", "no_merge"}
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
    skip_get=False,
    skip_regrid=False,
    skip_merge=False,
    preview=False,
    cfg=None,
    client=None,
):
    """
    Execute the forcing extraction workflow.

    This is the shared core used by both run_from_cli and case.py's process_forcings.
    Each boolean flag enables the corresponding component. If client is None, a
    LocalCluster with n_workers=1 is created and closed on exit.

    Args:
        ic:                  Run initial conditions
        bc:                  Run boundary conditions (OBC)
        bgcic:               Run BGC initial conditions
        bgcironforcing:      Run BGC iron forcing
        tides:               Run tidal forcing
        chl:                 Run chlorophyll processing
        runoff:              Run runoff mapping
        bgcrivernutrients:   Run BGC river nutrients (requires runoff first)
        skip_get:            Skip raw data download step
        skip_regrid:         Skip regridding step
        skip_merge:          Skip merge step
        preview:             Preview task graph without executing
        cfg:                 Config object; loaded from CONFIG_PATH if None
        client:              Dask client; a LocalCluster client is created if None
    """
    if cfg is None:
        cfg = utils.Config(CONFIG_PATH)

    own_client = client is None
    if own_client:
        client = utils.make_client(n_workers=1)

    try:
        if bc:
            process_obc(
                config_path=CONFIG_PATH,
                skip_get=skip_get,
                skip_regrid=skip_regrid,
                skip_merge=skip_merge,
                client=client,
                preview=preview,
            )

        tasks = []

        if ic:
            tasks.append(
                dask.delayed(initial_condition.process_initial_condition)(
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
            )

        if bgcic:
            tasks.append(dask.delayed(process_bgcic)())

        if bgcironforcing:
            tasks.append(dask.delayed(process_bgcironforcing)())

        if tides:
            tasks.append(dask.delayed(process_tides)())

        if chl:
            tasks.append(dask.delayed(process_chl)())

        if runoff:
            runoff_task = dask.delayed(process_runoff)()
            if bgcrivernutrients:
                tasks.append(
                    dask.delayed(_after)(runoff_task, process_bgcrivernutrients)
                )
            else:
                tasks.append(runoff_task)
        elif bgcrivernutrients:
            tasks.append(dask.delayed(process_bgcrivernutrients)())

        if not tasks:
            if not bc:
                print("No components selected.")
            return

        futures = client.compute(tasks)
        for future in as_completed(futures):
            exc = future.exception()
            if exc:
                raise exc
    finally:
        if own_client:
            client.close()


def run_from_cli(args, cfg, client):
    """
    Execute the forcing extraction workflow based on CLI arguments.

    Args:
        args: Parsed and resolved command-line arguments
        cfg: Config object from utils.Config(CONFIG_PATH)
        client: Dask client
    """
    if args.test:
        test_driver()
        return

    args = resolve_components(args, cfg)

    run_workflow(
        ic=args.ic,
        bc=args.bc,
        bgcic=args.bgcic,
        bgcironforcing=args.bgcironforcing,
        tides=args.tides,
        chl=args.chl,
        runoff=args.runoff,
        bgcrivernutrients=args.bgcrivernutrients,
        skip_get=args.no_get,
        skip_regrid=args.no_regrid,
        skip_merge=args.no_merge,
        preview=cfg["basic"]["general"].get("preview", False),
        cfg=cfg,
        client=client,
    )


if __name__ == "__main__":
    args = parse_args()
    cfg = utils.Config(CONFIG_PATH)
    client = utils.make_client(args.scheduler, args.n_workers, args.threads_per_worker)
    print(f"Dask dashboard: {client.dashboard_link}")
    run_from_cli(args, cfg, client=client)
    client.close()
