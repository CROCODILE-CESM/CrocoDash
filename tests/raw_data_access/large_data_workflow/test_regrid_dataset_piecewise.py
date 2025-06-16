from pathlib import Path
from CrocoDash.raw_data_access.large_data_workflow.code import (
    regrid_dataset_piecewise as rb,
)
from CrocoDash.raw_data_access import driver as dv
import pytest
from datetime import datetime


@pytest.mark.slow
def test_regrid_data_piecewise_workflow(
    generate_piecewise_raw_data,
    dummy_forcing_factory,
    tmp_path,
    get_rect_grid,
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
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "east_unprocessed_")
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "south_unprocessed_")
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
        run_initial_condition=False,
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


def test_regrid_data_piecewise_parsing(
    generate_piecewise_raw_data,
    dummy_forcing_factory,
    tmp_path,
    get_rect_grid,
    get_vgrid,
):

    # Get Grids
    grid = get_rect_grid
    vgrid = get_vgrid
    vgrid_path = tmp_path / "vgrid.nc"
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    vgrid.write(vgrid_path)

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
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "east_unprocessed_")
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "south_unprocessed_")
    )
    ds.to_netcdf(directory_raw_data / "ic_unprocessed.nc")

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
    preview_dict = rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200106",
        hgrid_path,
        varnames,
        output_folder,
        {"east": 1, "south": 2},
        run_initial_condition=True,
        vgrid_path=vgrid_path,
        preview=True,
    )
    for boundary_str, name in [("001", "east"), ("002", "south")]:
        file_start_date = "20200101"
        file_end_date = "20200106"
        file_start, file_end, file_path = preview_dict["matching_files"][name][0]
        assert file_start == datetime.strptime(file_start_date, "%Y%m%d")
        assert file_end == datetime.strptime(file_end_date, "%Y%m%d")
        assert file_path == str(
            directory_raw_data
            / f"{name}_unprocessed_{file_start_date}_{file_end_date}.nc"
        )
        assert preview_dict["output_file_names"][
            0
        ] == "forcing_obc_segment_{}_{}_{}.nc".format(
            boundary_str, file_start_date, file_end_date
        ) or preview_dict[
            "output_file_names"
        ][
            1
        ] == "forcing_obc_segment_{}_{}_{}.nc".format(
            boundary_str, file_start_date, file_end_date
        )
    assert "init_eta.nc" in preview_dict["output_file_names"]
    assert (
        directory_raw_data / "ic_unprocessed.nc"
        == preview_dict["matching_files"]["IC"][0][2]
    )
    new_output_folder = output_folder / "other_data"
    new_output_folder.mkdir()
    preview_dict = rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200107",
        "20200131",
        hgrid_path,
        varnames,
        new_output_folder,
        {"east": 1, "south": 2},
        run_initial_condition=False,
        preview=True,
    )
    for boundary_str in ["001", "002"]:
        file_start_date = "20200131"
        file_end_date = "20200131"
        assert (
            "forcing_obc_segment_{}_{}_{}.nc".format(
                boundary_str, file_start_date, file_end_date
            )
        ) in preview_dict["output_file_names"]
        file_start_date = "20200101"
        file_end_date = "20200106"
        assert (
            new_output_folder
            / "forcing_obc_segment_{}_{}_{}.nc".format(
                boundary_str, file_start_date, file_end_date
            )
        ) not in preview_dict["output_file_names"]
