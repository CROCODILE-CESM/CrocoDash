from CrocoDash.data_access.large_data_workflow.code import get_data_piecewise as dp
import os
import pytest

@pytest.mark.slow
def test_get_data_piecewise(tmp_path, get_rect_grid, skip_if_not_glade):
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    dp.get_data_piecewise(
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

    # This extra call takes a while to run
    dp.get_data_piecewise(
        "GLORYS",
        "get_glorys_data_from_rda",
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
