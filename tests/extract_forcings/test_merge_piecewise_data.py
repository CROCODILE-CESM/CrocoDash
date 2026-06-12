from pathlib import Path
from CrocoDash.extract_forcings import (
    merge_piecewise_dataset as md,
)
import xarray as xr
from datetime import datetime
import os
import threading
import pandas as pd
import dask
import pytest
from CrocoDash.grid import Grid


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
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
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
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
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
    assert "init_eta_filled.nc" in preview_dict["output_file_names"]
    assert (
        str(regridded_data_path / f"init_eta_filled.nc")
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


@pytest.mark.slow
def test_merge_piecewise_dataset_concurrent_dask(
    tmp_path, dummy_mom6_obc_data_factory, get_rect_grid
):
    """
    Verifies merge_piecewise_dataset is correct under concurrent dask-threaded reads.

    With chunks={"time": 1}, dask's threaded scheduler reads one HDF5 chunk per
    worker. Without lock=threading.Lock() in open_mfdataset, systems where HDF5 is
    not built with --enable-threadsafe raise RuntimeError: NetCDF: HDF error. The
    lock serializes reads for portability. This test checks correctness (no crash,
    valid output) under that load: 4 outer threads x 4 dask workers.
    """
    grid = get_rect_grid
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_mom6_obc_data_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
        "001",
        6,
    )

    # Write as HDF5 — the scipy/NetCDF3 backend is thread-safe and won't trigger the bug
    data_dir = tmp_path / "piecewise"
    data_dir.mkdir()
    current_date = pd.to_datetime("2020-01-01")
    end_date = pd.to_datetime("2020-01-31")
    while current_date <= end_date:
        next_date = min(current_date + pd.Timedelta(days=5), end_date)
        fname = (
            data_dir
            / f"forcing_obc_segment_001_{current_date.strftime('%Y%m%d')}_{next_date.strftime('%Y%m%d')}.nc"
        )
        ds.to_netcdf(fname, engine="netcdf4")
        current_date = next_date + pd.Timedelta(days=1)

    errors = []

    def run_merge(output_dir):
        try:
            with dask.config.set(scheduler="threads", num_workers=4):
                md.merge_piecewise_dataset(
                    data_dir,
                    "forcing_obc_segment_(\\d{3})_(\\d{8})_(\\d{8})\\.nc",
                    "%Y%m%d",
                    "20200101",
                    "20200131",
                    {"east": 1},
                    output_dir,
                    run_initial_condition=False,
                )
        except Exception as e:
            errors.append(e)

    output_dirs = [tmp_path / f"output_{i}" for i in range(4)]
    for d in output_dirs:
        d.mkdir()

    threads = [threading.Thread(target=run_merge, args=(d,)) for d in output_dirs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"HDF5 threading errors: {errors}"
    for d in output_dirs:
        assert (d / "forcing_obc_segment_001.nc").exists()
