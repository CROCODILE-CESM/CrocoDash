import pytest
import numpy as np
import pandas as pd
import xarray as xr
from datetime import datetime
from pathlib import Path

import CrocoDash.extract_forcings.obc as obc_module
from CrocoDash.extract_forcings.obc import (
    process_obc_conditions,
    _merge_boundary,
    _validate_coverage,
    _ocean_bbox_for_boundary,
)
from CrocoDash.extract_forcings.utils import is_valid_netcdf
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo


def test_date_string_slice_includes_noon_stamped_trailing_day():
    """The per-regrid-chunk slice uses date strings (not chunk_start/chunk_end
    datetimes) because pandas partial-string indexing covers the end string's
    whole calendar day. Daily-mean products like GLORYS stamp each day's value
    at noon, so a midnight-anchored datetime slice would exclude a single-day
    trailing chunk (e.g. a date range that isn't an exact multiple of
    regrid_step_days) entirely, crashing downstream on a zero-size array.
    """
    times = pd.date_range("2020-01-01 12:00", periods=16, freq="D")
    ds_full = xr.Dataset({"var": ("time", np.arange(16))}, coords={"time": times})

    chunk_start, chunk_end = datetime(2020, 1, 16), datetime(2020, 1, 16)
    start_str = chunk_start.strftime("%Y-%m-%d")
    end_str = chunk_end.strftime("%Y-%m-%d")

    sliced = ds_full.sel(time=slice(start_str, end_str))
    assert sliced.sizes["time"] == 1
    assert sliced.time.values[0] == np.datetime64("2020-01-16T12:00:00")


# ---------------------------------------------------------------------------
# Fixture: minimal config.json that process_obc_conditions can load
# ---------------------------------------------------------------------------


@pytest.fixture
def obc_config(tmp_path, get_rect_grid):
    grid = get_rect_grid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    raw_dir = tmp_path / "raw"
    regridded_dir = tmp_path / "regridded"
    output_dir = tmp_path / "output"
    raw_dir.mkdir()
    regridded_dir.mkdir()
    output_dir.mkdir()

    kwargs = dict(
        start_date="2020-01-01",
        end_date="2020-01-15",
        boundary_number_conversion={"east": 1, "south": 2},
        product_name="GLORYS",
        function_name="get_glorys_data_from_rda",
        product_info={
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
        hgrid_path=str(hgrid_path),
        raw_dataset_path=str(raw_dir),
        regridded_dataset_path=str(regridded_dir),
        output_path=str(output_dir),
        get_step_days=None,
        regrid_step_days=5,
    )
    return kwargs, tmp_path


# ---------------------------------------------------------------------------
# Regression: bathymetry_path must actually narrow the GET download bbox
# ---------------------------------------------------------------------------


def test_process_obc_conditions_uses_tmask_bbox_for_get(
    obc_config, get_rect_grid, monkeypatch, tmp_path
):
    """bathymetry_path is only useful if the tmask-derived per-boundary bbox
    it produces actually reaches the download call. process_obc_conditions
    computed `boundary_bboxes` from the tmask but never passed it to
    `_get_boundary`, which independently recomputed the *full* supergrid
    bbox regardless of bathymetry_path -- silently making the whole feature
    a no-op. This pins `_get_boundary` to receive the tmask-derived box, and
    that the box is actually narrower than the full-grid one (i.e. the test
    grid's land carving is doing something, not incidentally matching).
    """
    kwargs, case_tmp_path = obc_config
    grid = get_rect_grid

    # Carve land into the western half of the south edge so the south
    # boundary's tmask-derived bbox is narrower than the full grid edge.
    topo = Topo(grid=grid, min_depth=9.5, git=False)
    depth = np.full((grid.ny, grid.nx), 10.0)
    depth[0, : grid.nx // 2] = 0.0  # land: south row, western half
    topo.send_entire_depth_change_to_tcm(
        xr.DataArray(depth, dims=["ny", "nx"], attrs={"units": "m"})
    )
    bathymetry_path = tmp_path / "topo.nc"
    topo.write_topo(bathymetry_path)

    hgrid_path = Path(kwargs["hgrid_path"])
    hgrid_ds = xr.open_dataset(hgrid_path)
    full_south_bbox = Grid.get_bounding_boxes(hgrid_ds)["south"]
    expected_tmask_bbox = _ocean_bbox_for_boundary(
        hgrid_ds, topo.supergridmask, "south"
    )

    # The land carving should have actually narrowed the box -- otherwise
    # this test can't distinguish "tmask bbox used" from "full bbox used".
    assert expected_tmask_bbox["lon_min"] > full_south_bbox["lon_min"]

    captured_latlon = {}

    def fake_get_boundary(boundary, latlon, **_kwargs):
        captured_latlon[boundary] = latlon
        return []

    monkeypatch.setattr(obc_module, "_get_boundary", fake_get_boundary)
    monkeypatch.setattr(obc_module, "_regrid_boundary", lambda **_k: [])
    monkeypatch.setattr(obc_module, "_validate_coverage", lambda *a, **k: [])
    monkeypatch.setattr(obc_module, "_merge_boundary", lambda *a, **k: None)

    process_obc_conditions(**kwargs, bathymetry_path=bathymetry_path)

    assert captured_latlon["south"] == pytest.approx(expected_tmask_bbox)
    assert captured_latlon["south"] != pytest.approx(full_south_bbox)


# ---------------------------------------------------------------------------
# Preview: verify get_pairs and regrid_pairs are computed correctly
# ---------------------------------------------------------------------------


def test_preview_get_outputs(obc_config):
    kwargs, tmp_path = obc_config
    preview = process_obc_conditions(**kwargs, preview=True)

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
    bounds = Grid.get_bounding_boxes(grid)

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
    kwargs, tmp_path = obc_config
    grid = Grid.from_supergrid(tmp_path / "hgrid.nc")
    bounds = Grid.get_bounding_boxes(grid)
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

    process_obc_conditions(**kwargs)

    # regrid_step=5 → first chunk is 2020-01-01 to 2020-01-05
    assert (regridded_dir / "forcing_obc_segment_001_2020-01-01_2020-01-05.nc").exists()
    assert (regridded_dir / "forcing_obc_segment_002_2020-01-01_2020-01-05.nc").exists()


@pytest.mark.slow
def test_obc_merge_workflow(
    obc_config, generate_piecewise_raw_data, dummy_mom6_obc_data_factory, get_rect_grid
):
    kwargs, tmp_path = obc_config
    grid = get_rect_grid
    bounds = Grid.get_bounding_boxes(grid)
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
        ds.to_netcdf(raw_dir / f"{boundary}_unprocessed.2020-01-01_2020-01-15.nc")

    # regrid_step=5 → three regridded chunks per boundary
    for seg, ds in [("001", east), ("002", south)]:
        for fname in [
            f"forcing_obc_segment_{seg}_2020-01-01_2020-01-05.nc",
            f"forcing_obc_segment_{seg}_2020-01-06_2020-01-10.nc",
            f"forcing_obc_segment_{seg}_2020-01-11_2020-01-15.nc",
        ]:
            ds.to_netcdf(regridded_dir / fname)

    process_obc_conditions(**kwargs)

    for seg in ["001", "002"]:
        out = output_dir / f"forcing_obc_segment_{seg}.nc"
        assert out.exists()
        ds = xr.open_dataset(out)
        assert "time" in ds.dims
        ds.close()


# ---------------------------------------------------------------------------
# Unit tests: _validate_coverage (covers success, empty, wrong endpoints, gap, overlap)
# ---------------------------------------------------------------------------


def test_validate_coverage(tmp_path):
    start, end = datetime(2020, 1, 1), datetime(2020, 1, 15)

    def parse(f):
        s, e = f.stem.split("_")
        return datetime.fromisoformat(s), datetime.fromisoformat(e)

    good = [
        tmp_path / "2020-01-01_2020-01-05.nc",
        tmp_path / "2020-01-06_2020-01-10.nc",
        tmp_path / "2020-01-11_2020-01-15.nc",
    ]
    for f in good:
        f.touch()
    result = _validate_coverage(good, parse, "east", start, end)
    assert result == good

    with pytest.raises(FileNotFoundError):
        _validate_coverage([], parse, "east", start, end)

    bad_start = [tmp_path / "2020-01-03_2020-01-15.nc"]
    bad_start[0].touch()
    with pytest.raises(ValueError, match="starts"):
        _validate_coverage(bad_start, parse, "east", start, end)

    gap = [tmp_path / "2020-01-01_2020-01-05.nc", tmp_path / "2020-01-07_2020-01-15.nc"]
    for f in gap:
        f.touch()
    with pytest.raises(ValueError, match="Gap"):
        _validate_coverage(gap, parse, "east", start, end)

    overlap = [
        tmp_path / "2020-01-01_2020-01-05.nc",
        tmp_path / "2020-01-05_2020-01-15.nc",
    ]
    for f in overlap:
        f.touch()
    with pytest.raises(ValueError, match="Overlapping"):
        _validate_coverage(overlap, parse, "east", start, end)


# ---------------------------------------------------------------------------
# Unit tests: corruption detection
# ---------------------------------------------------------------------------


def test_is_valid_netcdf_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.nc"
    bad.write_bytes(b"not a netcdf file at all")
    assert not is_valid_netcdf(bad)


def test_merge_boundary_corrupt_existing_raises(
    tmp_path, dummy_mom6_obc_data_factory, get_rect_grid
):
    grid = get_rect_grid
    bounds = Grid.get_bounding_boxes(grid)
    east = dummy_mom6_obc_data_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
        "001",
        6,
    )
    regridded_dir = tmp_path / "regridded"
    regridded_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    chunk_file = regridded_dir / "forcing_obc_segment_001_2020-01-01_2020-01-05.nc"
    east.to_netcdf(chunk_file)

    merged = output_dir / "forcing_obc_segment_001.nc"
    merged.write_bytes(b"corrupted data")

    with pytest.raises(RuntimeError, match="not valid NetCDF"):
        _merge_boundary("001", [chunk_file], output_dir)
