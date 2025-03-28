from pathlib import Path
from CrocoDash.data_access.large_data_workflow.code import merge_piecewise_dataset as md
from CrocoDash.data_access import driver as dv
import pytest
import xarray as xr
import numpy as np
from datetime import datetime


def test_merge_piecewise_data(
    generate_piecewise_raw_data, tmp_path, dummy_mom6_obc_data_factory, get_rect_grid
):
    # Generate piecewise data

    # Get Grids
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    # Generate piecewise data
    piecewise_factory = generate_piecewise_raw_data
    bounds = dv.get_rectangular_segment_info(grid)
    east = dummy_mom6_obc_data_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
        "001",
        6,
    )
    south = dummy_mom6_obc_data_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
        "002",
        6,
    )
    regridded_data_path = Path(
        piecewise_factory(east, "2020-01-01", "2020-01-31", "forcing_obc_segment_001_")
    )
    regridded_data_path = Path(
        piecewise_factory(south, "2020-01-01", "2020-01-31", "forcing_obc_segment_002_")
    )
    output_folder = tmp_path / "output"
    output_folder.mkdir()

    # Regrid data
    md.merge_piecewise_dataset(
        regridded_data_path,
        "forcing_obc_segment_(\\d{3})_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200106",
        {"east": 1, "south": 2},
        output_folder,
    )
    start_date = datetime.strptime("20200101", "%Y%m%d")
    end_date = datetime.strptime("20200106", "%Y%m%d")
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format ##
    for boundary_str in ["001", "002"]:
        ds_path = output_folder / "forcing_obc_segment_{}.nc".format(boundary_str)
        assert (ds_path).exists()
        ds = xr.open_dataset(ds_path)
        assert len(ds["time"].values) == (end_date - start_date).days + 1
