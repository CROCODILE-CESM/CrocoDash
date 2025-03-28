from pathlib import Path
from CrocoDash.data_access.large_data_workflow import regrid_boundaries as rb
from CrocoDash.data_access import driver as dv
import pytest


@pytest.mark.slow
def test_regrid_data_piecewise(
    generate_piecewise_raw_data, dummy_forcing_factory, tmp_path, get_rect_grid
):

    # Get Grids
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    # Generate piecewise data
    piecewise_factory = generate_piecewise_raw_data
    bounds = dv.get_rectangular_segment_info(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "east_")
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "south_")
    )

    # Setup other required variables
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    varnames = {
        "time": "time",
        "yh": "latitude",
        "xh": "longitude",
        "zl": "depth",
        "eta": "zos",
        "u": "uo",
        "v": "vo",
        "tracers": {"salt": "so", "temp": "thetao"},
    }

    # Regrid data
    rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200106",
        hgrid_path,
        varnames,
        output_folder,
        {"east": 1, "south": 2},
    )
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format ##
    for boundary_str in ["001", "002"]:
        for file_start_date, file_end_date in [("20200101", "20200106")]:
            assert (
                output_folder
                / "forcing_obc_segment_{}_{}_{}.nc".format(
                    boundary_str, file_start_date, file_end_date
                )
            ).exists()
    new_output_folder = output_folder / "other_data"
    new_output_folder.mkdir()
    rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200107",
        "20200131",
        hgrid_path,
        varnames,
        new_output_folder,
        {"east": 1, "south": 2},
    )
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format and doesn't include files we don't want regridded##
    for boundary_str in ["001", "002"]:
        for file_start_date, file_end_date in [("20200131", "20200131")]:
            assert (
                new_output_folder
                / "forcing_obc_segment_{}_{}_{}.nc".format(
                    boundary_str, file_start_date, file_end_date
                )
            ).exists()
        for file_start_date, file_end_date in [("20200101", "20200106")]:
            assert not (
                new_output_folder
                / "forcing_obc_segment_{}_{}_{}.nc".format(
                    boundary_str, file_start_date, file_end_date
                )
            ).exists()
