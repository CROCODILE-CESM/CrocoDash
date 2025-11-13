from pathlib import Path
from CrocoDash.extract_forcings.code import (
    merge_piecewise_dataset as md,
)
from CrocoDash.raw_data_access import driver as dv
import xarray as xr
from datetime import datetime
import os
import pytest

@pytest.mark.slow
def test_merge_piecewise_data_workflow(
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
        run_initial_condition=False,
    )
    start_date = datetime.strptime("20200101", "%Y%m%d")
    end_date = datetime.strptime("20200106", "%Y%m%d")
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format ##
    for boundary_str in ["001", "002"]:
        ds_path = output_folder / "forcing_obc_segment_{}.nc".format(boundary_str)
        assert (ds_path).exists()
        ds = xr.open_dataset(ds_path)
        assert len(ds["time"].values) == (end_date - start_date).days + 1


def test_merge_piecewise_data_parsing(
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
    south.to_netcdf(regridded_data_path / "init_eta_filled.nc")
    south.to_netcdf(regridded_data_path / "init_tracers_filled.nc")
    south.to_netcdf(regridded_data_path / "init_vel_filled.nc")
    output_folder = tmp_path / "output"
    output_folder.mkdir()

    # Regrid data
    preview_dict = md.merge_piecewise_dataset(
        regridded_data_path,
        "forcing_obc_segment_(\\d{3})_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200106",
        {"east": 1, "south": 2},
        output_folder,
        run_initial_condition=True,
        preview=True,
    )
    assert str(preview_dict["output_folder"]) == str(output_folder)
    start_date = datetime.strptime("20200101", "%Y%m%d")
    end_date = datetime.strptime("20200106", "%Y%m%d")
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format ##
    for boundary_str in ["001", "002"]:
        ds_path = "forcing_obc_segment_{}.nc".format(boundary_str)
        assert (ds_path) in preview_dict["output_file_names"]
        assert (
            str(
                regridded_data_path
                / f"forcing_obc_segment_{boundary_str}_20200101_20200106.nc"
            )
            in preview_dict["matching_files"][boundary_str]
        )

    # Assert IC
    assert "init_eta.nc" in preview_dict["output_file_names"]
    assert (
        str(regridded_data_path / f"init_eta.nc")
        in preview_dict["matching_files"]["IC"]
    )

    preview_dict = md.merge_piecewise_dataset(
        regridded_data_path,
        "forcing_obc_segment_(\\d{3})_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200107",
        {"east": 1, "south": 2},
        output_folder,
        run_initial_condition=False,
        preview=True,
    )
    assert str(preview_dict["output_folder"]) == str(output_folder)
    start_date = datetime.strptime("20200101", "%Y%m%d")
    end_date = datetime.strptime("20200107", "%Y%m%d")
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format ##
    for boundary_str in ["001", "002"]:
        ds_path = "forcing_obc_segment_{}.nc".format(boundary_str)
        assert (ds_path) in preview_dict["output_file_names"]
        assert (
            str(
                regridded_data_path
                / f"forcing_obc_segment_{boundary_str}_20200101_20200106.nc"
            )
            in preview_dict["matching_files"][boundary_str]
        )
        assert (
            str(
                regridded_data_path
                / f"forcing_obc_segment_{boundary_str}_20200107_20200112.nc"
            )
            in preview_dict["matching_files"][boundary_str]
        )
