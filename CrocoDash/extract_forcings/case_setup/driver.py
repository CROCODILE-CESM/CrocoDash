"""CrocoDash Forcing Extraction Driver

This module orchestrates the forcing extraction workflow for a CrocoDash case.
It coordinates multiple forcing data sources (tides, runoff, BGC, etc.) and processes them
into MOM6-compatible file formats.

The script can be run from the command line with various component flags to control which
forcings are processed. It loads configuration from config.json and coordinates all extraction,
regridding, and formatting operations.

Typical CLI usage::

    python driver.py --all
    python driver.py --bc
    python driver.py --tides --bgcic
    python driver.py --all --skip runoff

Typical Python usage::

    from CrocoDash.extract_forcings.case_setup.driver import run_workflow
    run_workflow(bc=True, ic=True)
"""

import sys
import time
from pathlib import Path
import argparse

from CrocoDash.extract_forcings import (
    bgc,
    runoff as rof,
    tides,
    chlorophyll as chl,
    ww3,
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
        MARBL_FESEDFLUXRED_FILE=config["bgcironforcing"]["outputs"][
            "MARBL_FESEDFLUXRED_FILE"
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


def process_ww3():
    """Generate WW3 boundary spectra, spec list, and bounc namelist."""
    config = utils.Config(CONFIG_PATH)
    ww3.process_ww3_obc(
        ocn_grid=config.ocn_grid,
        inputdir=config.inputdir,
        boundaries=config["ww3"]["inputs"]["boundaries"],
        date_range=(config["basic"]["dates"]["start"], config["basic"]["dates"]["end"]),
        ww3_obc_product_name=config["ww3"]["inputs"]["ww3_obc_product_name"],
        ww3_obc_function_name=config["ww3"]["inputs"]["ww3_obc_function_name"],
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
    components.add_argument(
        "--ww3",
        action="store_true",
        help="Run WW3 boundary condition spectra generation",
    )

    top.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Skip components by name (e.g. --skip tides runoff)",
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
    ww3=False,
    preview=False,
    cfg=None,
):
    """
    Execute the forcing extraction workflow.

    This is the shared core used by both run_from_cli and case.py's process_forcings.
    Each boolean flag enables the corresponding component. All steps run sequentially.

    Args:
        ic:                  Run initial conditions
        bc:                  Run boundary conditions (OBC)
        bgcic:               Run BGC initial conditions
        bgcironforcing:      Run BGC iron forcing
        tides:               Run tidal forcing
        chl:                 Run chlorophyll processing
        runoff:              Run runoff mapping
        bgcrivernutrients:   Run BGC river nutrients (always runs after runoff)
        ww3:                 Run WW3 boundary condition spectra generation
        preview:             Preview task graph without executing
        cfg:                 Config object; loaded from CONFIG_PATH if None
    """
    if cfg is None:
        cfg = utils.Config(CONFIG_PATH)

    if not any(
        [ic, bc, bgcic, bgcironforcing, tides, chl, runoff, bgcrivernutrients, ww3]
    ):
        print("No components selected.")
        return

    timings = {}

    if bc:
        _t = time.perf_counter()
        process_obc(
            config_path=CONFIG_PATH,
            preview=preview,
        )
        timings["bc"] = time.perf_counter() - _t

    if ic:
        _t = time.perf_counter()
        initial_condition.process_initial_condition(
            product_name=cfg["basic"]["forcing"]["product_name"],
            function_name=cfg["basic"]["forcing"]["function_name"],
            product_information=cfg["basic"]["forcing"]["information"],
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

    if ww3:
        _t = time.perf_counter()
        process_ww3()
        timings["ww3"] = time.perf_counter() - _t

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

    args = resolve_components(args, cfg)

    workflow_kwargs = dict(
        ic=args.ic,
        bc=args.bc,
        bgcic=args.bgcic,
        bgcironforcing=args.bgcironforcing,
        tides=args.tides,
        chl=args.chl,
        runoff=args.runoff,
        bgcrivernutrients=args.bgcrivernutrients,
        ww3=args.ww3,
        preview=cfg["basic"]["general"].get("preview", False),
        cfg=cfg,
    )

    run_workflow(**workflow_kwargs)


if __name__ == "__main__":  # pragma: no cover
    args = parse_args()
    cfg = utils.Config(CONFIG_PATH)
    run_from_cli(args, cfg)
