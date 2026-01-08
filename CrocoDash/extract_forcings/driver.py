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
):
    """
    Driver file to run the large data workflow
    """
    workflow_dir = Path(__file__).parent

    # Read in config
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)

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
                file_path=config["bgcic"]["marbl_ic_filepath"],
                output_path=config["bgcic"]["MARBL_TRACERS_IC_FILE"],
            )
        elif key == "bgcironforcing" and (
            "process_bgcironforcing" not in kwargs or kwargs["process_bgcironforcing"]
        ):
            bgc.process_bgc_iron_forcing(
                nx=config["BGCIronForcing"]["nx"],
                ny=config["BGCIronForcing"]["ny"],
                MARBL_FESEDFLUX_FILE=config["BGCIronForcing"]["MARBL_FESEDFLUX_FILE"],
                MARBL_FEVENTFLUX_FILE=config["BGCIronForcing"]["MARBL_FEVENTFLUX_FILE"],
                inputdir=config["BGCIronForcing"]["inputdir"],
            )
        elif key == "bgcrivernutrients" and (
            "process_bgcrivernutrients" not in kwargs
            or kwargs["process_bgcrivernutrients"]
        ):
            bgc.process_bgc_river_nutrients(
                nx=config["BGCRiverNutrients"]["nx"],
                ny=config["BGCRiverNutrients"]["ny"],
                ocn_grid=config["BGCRiverNutrients"]["ocn_grid"],
                river_nutrients_nnsm_filepath=config["BGCRiverNutrients"][
                    "river_nutrients_nnsm_filepath"
                ],
                ROF2OCN_LIQ_RMAPNAME=config["BGCRiverNutrients"][
                    "ROF2OCN_LIQ_RMAPNAME"
                ],
            )
        elif key == "runoff" and (
            "process_runoff" not in kwargs or kwargs["process_runoff"]
        ):
            rof.generate_rof_ocn_map(
                rof_grid_name=config["runoff"]["rof_grid_name"],
                rof_esmf_mesh_filepath=config["runoff"]["rof_esmf_mesh_filepath"],
                inputdir=config["basic"]["paths"]["output_path"],
                grid_name=config["basic"]["forcing"]["information"]["grid_name"],
                rmax=config["runoff"]["rmax"],
                fold=config["runoff"]["fold"],
                runoff_esmf_mesh_path=config["runoff"]["runoff_esmf_mesh_path"],
            )
        elif key == "tides" and (
            "process_tides" not in kwargs or kwargs["process_tides"]
        ):
            tides.process_tides(None)
        elif key == "chl" and ("process_chl" not in kwargs or kwargs["process_chl"]):
            chl.interpolate_and_fill_seawifs(
                ocn_grid=ocn_grid,
                ocn_topo=ocn_topo,
                chl_processed_filepath=config["chl"]["chl_processed_filepath"],
                output_filepath=config["chl"]["output_filepath"],
            )
    return


if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_driver()
    else:
        main()
