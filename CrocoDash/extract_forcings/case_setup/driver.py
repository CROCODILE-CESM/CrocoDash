import sys
import json
from pathlib import Path
import argparse


from CrocoDash.extract_forcings import (
    merge_piecewise_dataset as mpd,
    get_dataset_piecewise as gdp,
    regrid_dataset_piecewise as rdp,
    bgc,
    runoff as rof,
    tides,
    chlorophyll as chl,
    utils as utils,
)


CONFIG_PATH = Path(__file__).parent / "config.json"


def test_driver():
    """Test that all the imports work"""
    print("All Imports Work!")
    config = utils.Config(CONFIG_PATH)
    print("Config Loads!")
    return


def process_bgcic():
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


def process_conditions(
    get_dataset_piecewise=True,
    regrid_dataset_piecewise=True,
    merge_piecewise_dataset=True,
    run_initial_condition=True,
    run_boundary_conditions=True,
):
    config = utils.Config(CONFIG_PATH)

    # Call get_dataset_piecewise
    if get_dataset_piecewise:
        gdp.get_dataset_piecewise(
            product_name=config["basic"]["forcing"]["product_name"],
            function_name=config["basic"]["forcing"]["function_name"],
            product_information=config["basic"]["forcing"]["information"],
            date_format=config["basic"]["dates"]["format"],
            start_date=config["basic"]["dates"]["start"],
            end_date=config["basic"]["dates"]["end"],
            hgrid_path=config["basic"]["paths"]["hgrid_path"],
            step_days=int(config["basic"]["general"]["step"]),
            output_dir=config["basic"]["paths"]["raw_dataset_path"],
            boundary_number_conversion=config["basic"]["general"][
                "boundary_number_conversion"
            ],
            run_initial_condition=run_initial_conditions,
            run_boundary_conditions=run_boundary_conditions,
            preview=config["basic"]["general"]["preview"],
        )

    # Call regrid_dataset_piecewise
    if regrid_dataset_piecewise:
        rdp.regrid_dataset_piecewise(
            config["basic"]["paths"]["raw_dataset_path"],
            config["basic"]["file_regex"]["raw_dataset_pattern"],
            config["basic"]["dates"]["format"],
            config["basic"]["dates"]["start"],
            config["basic"]["dates"]["end"],
            config["basic"]["paths"]["hgrid_path"],
            config["basic"]["paths"]["bathymetry_path"],
            config["basic"]["forcing"]["information"],
            config["basic"]["paths"]["regridded_dataset_path"],
            config["basic"]["general"]["boundary_number_conversion"],
            run_initial_condition,
            run_boundary_conditions,
            config["basic"]["paths"]["vgrid_path"],
            config["basic"]["general"]["preview"],
        )

    # Call merge_dataset_piecewise
    if merge_piecewise_dataset:
        mpd.merge_piecewise_dataset(
            config["basic"]["paths"]["regridded_dataset_path"],
            config["basic"]["file_regex"]["regridded_dataset_pattern"],
            config["basic"]["dates"]["format"],
            config["basic"]["dates"]["start"],
            config["basic"]["dates"]["end"],
            config["basic"]["general"]["boundary_number_conversion"],
            config["basic"]["paths"]["output_path"],
            run_initial_condition,
            run_boundary_conditions,
            config["basic"]["general"]["preview"],
        )


def process_runoff():
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
    config = utils.Config(CONFIG_PATH)
    chl.process_chl(
        ocn_grid=config.ocn_grid,
        ocn_topo=config.ocn_topo,
        inputdir=config.inputdir,
        chl_processed_filepath=config["chl"]["inputs"]["chl_processed_filepath"],
        output_filepath=config["chl"]["outputs"]["CHL_FILE"],
    )


def should_run(name, args, cfg):
    skip = set(args.skip or [])
    skip = {s.lower() for s in (args.skip or [])}
    not_skipped = name.lower() not in skip
    requested = args.all or getattr(args, name)
    exists = name in cfg.config.keys()

    if requested and not exists:
        print(f"[skip] '{name}' requested but not in config")

    if requested and not not_skipped:
        print(f"[skip] '{name}' skipped via --skip")

    return requested and exists and not_skipped


def resolve_icbcconditions(args):
    if args.all:
        return True, True
    return args.ic, args.bc


def parse_args():
    parser = argparse.ArgumentParser(description="CrocoDash forcing workflow driver")

    top = parser.add_argument_group("Top-level actions")
    top.add_argument("--all", action="store_true", help="Run all components")
    top.add_argument("--test", action="store_true", help="Run import/config test only")

    components = parser.add_argument_group("Forcing components")
    components.add_argument("--ic", action="store_true", help="Run initial conditions")
    components.add_argument("--bc", action="store_true", help="Run boundary conditions")
    components.add_argument("--bgcic", action="store_true")
    components.add_argument("--bgcironforcing", action="store_true")
    components.add_argument("--bgcrivernutrients", action="store_true")
    components.add_argument("--runoff", action="store_true")
    components.add_argument("--tides", action="store_true")
    components.add_argument("--chl", action="store_true")

    conditions_opts = parser.add_argument_group("Conditions options")
    conditions_opts.add_argument("--no-get", action="store_true")
    conditions_opts.add_argument("--no-regrid", action="store_true")
    conditions_opts.add_argument("--no-merge", action="store_true")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    return parser.parse_args()


def run_from_cli(args):
    cfg = utils.Config(CONFIG_PATH)

    if args.test:
        test_driver()
        return

    run_ic, run_bc = resolve_conditions(args)
    # Conditions pipeline is special (comes from "basic")
    if (args.all or args.conditions) and "conditions" not in (args.skip or []):
        process_conditions(
            get_dataset_piecewise=not args.no_get,
            regrid_dataset_piecewise=not args.no_regrid,
            merge_piecewise_dataset=not args.no_merge,
            run_initial_condition=run_ic,
            run_boundary_conditions=run_bc,
        )

    if should_run("bgcic", args, cfg):
        process_bgcic()

    if should_run("bgcironforcing", args, cfg):
        process_bgcironforcing()

    if should_run("runoff", args, cfg):
        process_runoff()

    # runoff-dependent product
    if should_run("bgcrivernutrients", args, cfg):
        process_bgcrivernutrients()

    if should_run("tides", args, cfg):
        process_tides()

    if should_run("chl", args, cfg):
        process_chl()


if __name__ == "__main__":

    args = parse_args()
    run_from_cli(args)
