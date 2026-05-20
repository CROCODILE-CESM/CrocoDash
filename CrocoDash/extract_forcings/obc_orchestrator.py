from CrocoDash.extract_forcings import (
    merge_piecewise_dataset as mpd,
    get_dataset_piecewise as gdp,
    regrid_dataset_piecewise as rdp,
    utils,
)


def process_conditions(
    config_path,
    get_dataset_piecewise=True,
    regrid_dataset_piecewise=True,
    merge_piecewise_dataset=True,
    run_initial_condition=True,
    run_boundary_conditions=True,
    client=None,
):
    """
    Process initial and/or boundary conditions through the three-step pipeline.

    This function orchestrates the data extraction workflow:
    1. get_dataset_piecewise: Download/retrieve raw data from source datasets
    2. regrid_dataset_piecewise: Regrid data to your custom regional grid
    3. merge_piecewise_dataset: Merge regridded data into final forcing files

    Args:
        get_dataset_piecewise: Whether to download raw data (can skip if already cached)
        regrid_dataset_piecewise: Whether to regrid data to regional grid
        merge_piecewise_dataset: Whether to merge data into final files
        run_initial_condition: Whether to process initial conditions (t=0)
        run_boundary_conditions: Whether to process boundary conditions (open boundaries)
        client: The dask client to use
    """
    config = utils.Config(config_path)

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
            run_initial_condition=run_initial_condition,
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
