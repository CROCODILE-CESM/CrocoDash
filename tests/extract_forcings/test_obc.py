import json
import pytest
import numpy as np
import xarray as xr
from datetime import datetime
from pathlib import Path

from CrocoDash.extract_forcings.obc import (
    process_obc_conditions,
    _merge_boundary,
)
from CrocoDash.grid import Grid

# ---------------------------------------------------------------------------
# Fixture: minimal config.json that process_obc_conditions can load
# ---------------------------------------------------------------------------


@pytest.fixture
def obc_config(tmp_path, get_rect_grid):
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    # Minimal bathymetry file -must match grid dims (ny=30, nx=40 for this grid)
    # Config.__init__ reads min_depth from attrs
    topo_ds = xr.Dataset(
        {"depth": (["ny", "nx"], np.full((30, 40), 100.0))},
        attrs={"min_depth": 9.5},
    )
    topo_path = tmp_path / "topo.nc"
    topo_ds.to_netcdf(topo_path)

    raw_dir = tmp_path / "raw"
    regridded_dir = tmp_path / "regridded"
    output_dir = tmp_path / "output"
    raw_dir.mkdir()
    regridded_dir.mkdir()
    output_dir.mkdir()

    config = {
        "basic": {
            "dates": {
                "format": "%Y%m%d",
                "start": "20200101",
                "end": "20200115",
            },
            "general": {
                "get_step": None,
                "regrid_step": 5,
                "boundary_number_conversion": {"east": 1, "south": 2},
                "preview": False,
            },
            "forcing": {
                "product_name": "GLORYS",
                "function_name": "get_glorys_data_from_rda",
                "information": {
                    "u_var_name": "uo",
                    "v_var_name": "vo",
                    "eta_var_name": "zos",
                    "tracer_var_names": {"temp": "thetao", "salt": "so"},
                    "time": "time",
                    "tracer_x_coord": "longitude",
                    "tracer_y_coord": "latitude",
                    "u_y_coord": "latitude",
                    "u_x_coord": "longitude",
                    "v_x_coord": "longitude",
                    "v_y_coord": "latitude",
                    "depth_coord": "depth",
                },
            },
            "paths": {
                "hgrid_path": str(hgrid_path),
                "bathymetry_path": str(topo_path),
                "raw_dataset_path": str(raw_dir),
                "regridded_dataset_path": str(regridded_dir),
                "output_path": str(output_dir),
                "input_dataset_path": str(tmp_path),
            },
        }
    }

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return config_path, tmp_path


# ---------------------------------------------------------------------------
# Preview: verify get_pairs and regrid_pairs are computed correctly
# ---------------------------------------------------------------------------


def test_preview_get_outputs(obc_config):
    config_path, tmp_path = obc_config
    preview = process_obc_conditions(config_path, preview=True)

    # get_step=None → one pair covering the full range
    assert len(preview["get_pairs"]) == 1
    assert preview["get_pairs"][0][0] == datetime.strptime("20200101", "%Y%m%d")
    assert preview["get_pairs"][0][1] == datetime.strptime("20200115", "%Y%m%d")

    # regrid_step=5 → three 5-day chunks: (01-05), (06-10), (11-15)
    assert len(preview["regrid_pairs"]) == 3
    assert preview["regrid_pairs"][0] == (
        datetime.strptime("20200101", "%Y%m%d"),
        datetime.strptime("20200105", "%Y%m%d"),
    )
    assert preview["regrid_pairs"][1] == (
        datetime.strptime("20200106", "%Y%m%d"),
        datetime.strptime("20200110", "%Y%m%d"),
    )
    assert preview["regrid_pairs"][2] == (
        datetime.strptime("20200111", "%Y%m%d"),
        datetime.strptime("20200115", "%Y%m%d"),
    )

    assert set(preview["boundaries"]) == {"east", "south"}


# ---------------------------------------------------------------------------
# Unit test: _merge_boundary - tests merge without any external data
# ---------------------------------------------------------------------------


def test_merge_single_boundary(
    tmp_path, generate_piecewise_raw_data, dummy_mom6_obc_data_factory, get_rect_grid
):
    grid = get_rect_grid
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)

    east = dummy_mom6_obc_data_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
        "001",
        6,
    )
    piecewise_factory = generate_piecewise_raw_data
    regridded_dir = Path(
        piecewise_factory(east, "2020-01-01", "2020-01-10", "forcing_obc_segment_001_")
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    chunk_files = sorted(regridded_dir.glob("forcing_obc_segment_001_*.nc"))
    assert len(chunk_files) > 0

    result = _merge_boundary("001", chunk_files, output_dir)

    assert result.exists()
    assert result.name == "forcing_obc_segment_001.nc"
    ds = xr.open_dataset(result)
    assert "time" in ds.dims
    ds.close()


# ---------------------------------------------------------------------------
# Slow integration tests (require real data access)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_obc_regrid_workflow(
    obc_config, generate_piecewise_raw_data, dummy_forcing_factory, skip_if_not_glade
):
    config_path, tmp_path = obc_config
    grid = Grid.from_supergrid(tmp_path / "hgrid.nc")
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    raw_dir = tmp_path / "raw"
    regridded_dir = tmp_path / "regridded"

    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    # get_step=None → one file covering the full range
    generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-15", "east_unprocessed.")
    generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-15", "south_unprocessed.")

    process_obc_conditions(config_path)

    # regrid_step=5 → first chunk is 20200101-20200105
    assert (regridded_dir / "forcing_obc_segment_001_20200101_20200105.nc").exists()
    assert (regridded_dir / "forcing_obc_segment_002_20200101_20200105.nc").exists()


@pytest.mark.slow
def test_obc_merge_workflow(
    obc_config, generate_piecewise_raw_data, dummy_mom6_obc_data_factory, get_rect_grid
):
    config_path, tmp_path = obc_config
    grid = get_rect_grid
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    raw_dir = tmp_path / "raw"
    regridded_dir = tmp_path / "regridded"
    output_dir = tmp_path / "output"

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
    # get_step=None → one raw file per boundary covering the full range
    for boundary, ds in [("east", east), ("south", south)]:
        ds.to_netcdf(raw_dir / f"{boundary}_unprocessed.20200101_20200115.nc")

    # regrid_step=5 → three regridded chunks per boundary
    for seg, ds in [("001", east), ("002", south)]:
        for fname in [
            f"forcing_obc_segment_{seg}_20200101_20200105.nc",
            f"forcing_obc_segment_{seg}_20200106_20200110.nc",
            f"forcing_obc_segment_{seg}_20200111_20200115.nc",
        ]:
            ds.to_netcdf(regridded_dir / fname)

    process_obc_conditions(config_path)

    for seg in ["001", "002"]:
        out = output_dir / f"forcing_obc_segment_{seg}.nc"
        assert out.exists()
        ds = xr.open_dataset(out)
        assert "time" in ds.dims
        ds.close()
