import json
import pytest
import numpy as np
import xarray as xr
from datetime import datetime
from pathlib import Path

from CrocoDash.extract_forcings.obc import (
    process_obc_conditions,
    _merge_single_boundary,
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
                "step": "5",
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
            "file_regex": {
                "raw_dataset_pattern": r"(east|south)_unprocessed\.(\d{8})_(\d{8})\.nc",
                "regridded_dataset_pattern": r"forcing_obc_segment_(\d{3})_(\d{8})_(\d{8})\.nc",
            },
        }
    }

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return config_path, tmp_path


# ---------------------------------------------------------------------------
# Preview: get step -tests date parsing and output file naming
# ---------------------------------------------------------------------------


def test_preview_get_outputs(obc_config):
    config_path, tmp_path = obc_config
    preview = process_obc_conditions(config_path, preview=True)

    # Date range: 20200101-20200115, step=5 -> chunks (01->06), (07->11), (12->15)
    assert preview["date_pairs"][0][0] == datetime.strptime("20200101", "%Y%m%d")
    assert preview["date_pairs"][-1][1] == datetime.strptime("20200115", "%Y%m%d")
    assert len(preview["date_pairs"]) == 3

    # Each boundary x chunk should have a named output file (non-overlapping dates)
    assert (
        preview["get_outputs"][("east", 0)].name
        == "east_unprocessed.20200101_20200106.nc"
    )
    assert (
        preview["get_outputs"][("south", 0)].name
        == "south_unprocessed.20200101_20200106.nc"
    )
    assert (
        preview["get_outputs"][("east", 1)].name
        == "east_unprocessed.20200107_20200111.nc"
    )
    assert (
        preview["get_outputs"][("east", 2)].name
        == "east_unprocessed.20200112_20200115.nc"
    )

    # When not skip_get, raw_inputs mirrors get_outputs
    assert preview["raw_inputs"] == preview["get_outputs"]


# ---------------------------------------------------------------------------
# Preview: regrid step -tests raw file discovery and regrid output naming
# ---------------------------------------------------------------------------


def test_preview_regrid_finds_raw_files(obc_config):
    config_path, tmp_path = obc_config
    raw_dir = tmp_path / "raw"

    # Date pairs for step=5, 20200101-20200115: (01->06), (07->11), (12->15) -non-overlapping
    # Put two raw files on disk for east boundary matching those pairs
    (raw_dir / "east_unprocessed.20200101_20200106.nc").touch()
    (raw_dir / "east_unprocessed.20200107_20200111.nc").touch()

    preview = process_obc_conditions(config_path, skip_get=True, preview=True)

    # Should find the two east files
    assert ("east", 0) in preview["raw_inputs"]
    assert ("east", 1) in preview["raw_inputs"]
    assert (
        preview["raw_inputs"][("east", 0)].name
        == "east_unprocessed.20200101_20200106.nc"
    )

    # Should NOT find south (no south files on disk)
    assert ("south", 0) not in preview["raw_inputs"]

    # Regrid outputs should be named correctly for found inputs
    assert (
        preview["regrid_outputs"][("east", 0)].name
        == "forcing_obc_segment_001_20200101_20200106.nc"
    )
    assert (
        preview["regrid_outputs"][("east", 1)].name
        == "forcing_obc_segment_001_20200107_20200111.nc"
    )


# ---------------------------------------------------------------------------
# Preview: merge step -tests regridded file discovery and merge output naming
# ---------------------------------------------------------------------------


def test_preview_merge_finds_regridded_files(obc_config):
    config_path, tmp_path = obc_config
    regridded_dir = tmp_path / "regridded"

    # Put regridded files on disk for both boundaries
    (regridded_dir / "forcing_obc_segment_001_20200101_20200106.nc").touch()
    (regridded_dir / "forcing_obc_segment_001_20200107_20200111.nc").touch()
    (regridded_dir / "forcing_obc_segment_002_20200101_20200106.nc").touch()

    preview = process_obc_conditions(
        config_path, skip_get=True, skip_regrid=True, preview=True
    )

    # Should discover both boundaries
    assert "001" in preview["regridded_inputs"]
    assert "002" in preview["regridded_inputs"]
    assert len(preview["regridded_inputs"]["001"]) == 2
    assert len(preview["regridded_inputs"]["002"]) == 1

    # Merge outputs should be named correctly
    assert preview["merge_outputs"]["001"].name == "forcing_obc_segment_001.nc"
    assert preview["merge_outputs"]["002"].name == "forcing_obc_segment_002.nc"


# ---------------------------------------------------------------------------
# Unit test: _merge_single_boundary -tests merge without any external data
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

    result = _merge_single_boundary("001", chunk_files, output_dir)

    assert result.exists()
    assert result.name == "forcing_obc_segment_001.nc"
    ds = xr.open_dataset(result)
    assert "time" in ds.dims
    ds.close()


# ---------------------------------------------------------------------------
# Slow integration tests (require real data access)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_obc_get_workflow(obc_config, skip_if_not_glade):
    config_path, tmp_path = obc_config
    raw_dir = tmp_path / "raw"
    process_obc_conditions(
        config_path,
        skip_regrid=True,
        skip_merge=True,
    )
    assert (raw_dir / "east_unprocessed.20200101_20200106.nc").exists()
    assert (raw_dir / "south_unprocessed.20200101_20200106.nc").exists()


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
    generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-15", "east_unprocessed.")
    generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-15", "south_unprocessed.")

    process_obc_conditions(config_path, skip_get=True, skip_merge=True)

    assert (regridded_dir / "forcing_obc_segment_001_20200101_20200106.nc").exists()
    assert (regridded_dir / "forcing_obc_segment_002_20200101_20200106.nc").exists()


@pytest.mark.slow
def test_obc_merge_workflow(
    obc_config, generate_piecewise_raw_data, dummy_mom6_obc_data_factory, get_rect_grid
):
    config_path, tmp_path = obc_config
    grid = get_rect_grid
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
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
    generate_piecewise_raw_data(
        east, "2020-01-01", "2020-01-15", "forcing_obc_segment_001_"
    )
    generate_piecewise_raw_data(
        south, "2020-01-01", "2020-01-15", "forcing_obc_segment_002_"
    )

    process_obc_conditions(config_path, skip_get=True, skip_regrid=True)

    for seg in ["001", "002"]:
        out = output_dir / f"forcing_obc_segment_{seg}.nc"
        assert out.exists()
        ds = xr.open_dataset(out)
        assert "time" in ds.dims
        ds.close()
