from CrocoDash.extract_forcings.code import (
    get_dataset_piecewise as dp,
)
import os
import pytest
from datetime import datetime


@pytest.mark.slow
def test_get_dataset_piecewise_workflow(tmp_path, get_rect_grid, skip_if_not_glade):
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    dp.get_dataset_piecewise(
        "GLORYS",
        "get_glorys_data_from_rda",
        "%Y%m%d",
        "20200101",
        "20200201",
        hgrid_path,
        5,
        tmp_path,
        {"east": 1, "west": 2, "north": 3, "south": 4},
    )

    assert os.path.exists(tmp_path / "east_unprocessed.20200101_20200106.nc")
    assert os.path.exists(tmp_path / "south_unprocessed.20200201_20200201.nc")
    assert os.path.exists(tmp_path / "ic_unprocessed.nc")

    # This extra call takes a while to run
    dp.get_dataset_piecewise(
        "GLORYS",
        "get_glorys_data_from_rda",
        {
            "time": "time",
            "tracer_x_coord": "longitude",
            "tracer_y_coord": "latitude",
            "u_var_name": "uo",
            "v_var_name": "vo",
            "u_y_coord": "latitude",
            "u_x_coord": "longitude",
            "v_x_coord": "longitude",
            "v_y_coord": "latitude",
            "eta_var_name": "zos",
            "depth_coord": "depth",
            "tracer_var_names": {"temp": "thetao", "salt": "so"},
        },
        "%Y%m%d",
        "20200130",
        "20200201",
        hgrid_path,
        5,
        tmp_path,
        {"north": 3, "south": 4},
    )

    assert os.path.exists(tmp_path / "south_unprocessed.20200130_20200201.nc")
    assert not os.path.exists(tmp_path / "east_unprocessed.20200130_20200201.nc")


def test_get_dataset_piecewise_parsing(tmp_path, get_rect_grid):
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    preview_dict = dp.get_dataset_piecewise(
        "GLORYS",
        "get_glorys_data_script_for_cli",
        {
            "time": "time",
            "tracer_x_coord": "longitude",
            "tracer_y_coord": "latitude",
            "u_var_name": "uo",
            "v_var_name": "vo",
            "u_y_coord": "latitude",
            "u_x_coord": "longitude",
            "v_x_coord": "longitude",
            "v_y_coord": "latitude",
            "eta_var_name": "zos",
            "depth_coord": "depth",
            "tracer_var_names": {"temp": "thetao", "salt": "so"},
        },
        "%Y%m%d",
        "20200101",
        "20200201",
        hgrid_path,
        5,
        tmp_path,
        {"east": 1},
        preview=True,
    )

    assert preview_dict["dates"][0] == datetime.strptime("20200101", "%Y%m%d")
    assert preview_dict["dates"][-1] == datetime.strptime("20200201", "%Y%m%d")
    assert (
        preview_dict["output_file_names"][1] == "east_unprocessed.20200101_20200106.nc"
    )
    assert preview_dict["output_file_names"][0] == "ic_unprocessed.nc"
    assert preview_dict["output_folder"] == tmp_path
