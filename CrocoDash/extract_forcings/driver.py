import sys
import json
from pathlib import Path

parent_dir = Path(__file__).parent
sys.path.append(str(parent_dir / "code"))
import merge_piecewise_dataset as mpd
import get_dataset_piecewise as gdp
import regrid_dataset_piecewise as rdp
import bgc
import runoff as rof
import tides
import chlorophyll as chl
from CrocoDash.topo import *
from CrocoDash.grid import *


def test_driver():
    """Test that all the imports work"""
    print("All Imports Work!")
    # Test Config
    workflow_dir = Path(__file__).parent
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    print("Config Loads!")
    return


def main(
    get_dataset_piecewise=True,
    regrid_dataset_piecewise=True,
    merge_piecewise_dataset=True,
    **kwargs,
):
    """
    Driver file to run the large data workflow
    """
    workflow_dir = Path(__file__).parent

    # Read in config
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    ocn_grid = Grid.from_supergrid(config["basic"]["paths"]["hgrid_path"])
    topo = xr.open_dataset(
        config["basic"]["paths"]["bathymetry_path"], decode_times=False
    )

    ocn_topo = Topo.from_topo_file(
        ocn_grid,
        config["basic"]["paths"]["bathymetry_path"],
        min_depth=topo.attrs["min_depth"],
    )

    inputdir = Path(config["basic"]["paths"]["input_dataset_path"])

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
            run_initial_condition=config["basic"]["general"]["run_initial_condition"],
            run_boundary_conditions=config["basic"]["general"][
                "run_boundary_conditions"
            ],
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
            config["basic"]["general"]["run_initial_condition"],
            config["basic"]["general"]["run_boundary_conditions"],
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
            config["basic"]["general"]["run_initial_condition"],
            config["basic"]["general"]["run_boundary_conditions"],
            config["basic"]["general"]["preview"],
        )

    for key in config.keys():
        if key == "basic":
            continue
        elif key == "bgcic" and (
            "process_bgcic" not in kwargs or kwargs["process_bgcic"]
        ):
            bgc.process_bgc_ic(
                file_path=config["bgcic"]["inputs"]["marbl_ic_filepath"],
                output_path=inputdir
                / "ocnice"
                / config["bgcic"]["outputs"]["MARBL_TRACERS_IC_FILE"],
            )
        elif key == "bgcironforcing" and (
            "process_bgcironforcing" not in kwargs or kwargs["process_bgcironforcing"]
        ):
            bgc.process_bgc_iron_forcing(
                nx=ocn_grid.nx,
                ny=ocn_grid.ny,
                MARBL_FESEDFLUX_FILE=config["bgcironforcing"]["outputs"][
                    "MARBL_FESEDFLUX_FILE"
                ],
                MARBL_FEVENTFLUX_FILE=config["bgcironforcing"]["outputs"][
                    "MARBL_FEVENTFLUX_FILE"
                ],
                inputdir=inputdir,
            )

        elif key == "runoff" and (
            "process_runoff" not in kwargs or kwargs["process_runoff"]
        ):
            rof.generate_rof_ocn_map(
                rof_grid_name=config["runoff"]["inputs"]["rof_grid_name"],
                rof_esmf_mesh_filepath=config["runoff"]["inputs"][
                    "rof_esmf_mesh_filepath"
                ],
                inputdir=inputdir,
                grid_name=config["runoff"]["inputs"]["case_grid_name"],
                rmax=config["runoff"]["inputs"]["rmax"],
                fold=config["runoff"]["inputs"]["fold"],
                runoff_esmf_mesh_path=config["runoff"]["inputs"][
                    "runoff_esmf_mesh_filepath"
                ],
            )
            if "bgcrivernutrients" in config.keys() and (
                "process_bgcrivernutrients" not in kwargs
                or kwargs["process_bgcrivernutrients"]
            ):
                bgc.process_river_nutrients(
                    ocn_grid=ocn_grid,
                    global_river_nutrients_filepath=config["bgcrivernutrients"][
                        "inputs"
                    ]["global_river_nutrients_filepath"],
                    ROF2OCN_LIQ_RMAPNAME=config["runoff"]["outputs"][
                        "ROF2OCN_LIQ_RMAPNAME"
                    ],
                    river_nutrients_nnsm_filepath=inputdir
                    / "ocnice"
                    / config["bgcrivernutrients"]["outputs"]["RIV_FLUX_FILE"],
                )
        elif key == "tides" and (
            "process_tides" not in kwargs or kwargs["process_tides"]
        ):
            tides.process_tides(
                ocn_topo=ocn_topo,
                inputdir=inputdir,
                supergrid_path=config["basic"]["paths"]["hgrid_path"],
                vgrid_path=config["basic"]["paths"]["vgrid_path"],
                tidal_constituents=config["tides"]["inputs"]["tidal_constituents"],
                boundaries=config["tides"]["inputs"]["boundaries"],
                tpxo_elevation_filepath=config["tides"]["inputs"][
                    "tpxo_elevation_filepath"
                ],
                tpxo_velocity_filepath=config["tides"]["inputs"][
                    "tpxo_velocity_filepath"
                ],
            )
        elif key == "chl" and ("process_chl" not in kwargs or kwargs["process_chl"]):
            chl.process_chl(
                ocn_grid=ocn_grid,
                ocn_topo=ocn_topo,
                inputdir=inputdir,
                chl_processed_filepath=config["chl"]["inputs"][
                    "chl_processed_filepath"
                ],
                output_filepath=config["chl"]["outputs"]["CHL_FILE"],
            )
    return


if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_driver()
    else:
        main()
