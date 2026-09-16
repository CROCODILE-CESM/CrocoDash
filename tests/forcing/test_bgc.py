"""Tests for the BGC-family configurators' process() methods."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import xarray as xr

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.raw_data_access.base import NOLEAP
from CrocoDash.forcing.bgc import (
    BGCICConfigurator,
    BGCIronForcingConfigurator,
    BGCRiverNutrientsConfigurator,
)


def _make_ctx(tmp_path, **overrides):
    defaults = dict(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path,
        config={},
    )
    defaults.update(overrides)
    return WorkflowContext(**defaults)


def test_bgcic_process_copies_file(tmp_path):
    src = tmp_path / "src.nc"
    src.write_bytes(b"hello")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    configurator = BGCICConfigurator(marbl_ic_filepath=src)
    configurator.set_output_param("MARBL_TRACERS_IC_FILE", "dst.nc")

    configurator.process(_make_ctx(tmp_path, output_path=out_dir))

    assert (out_dir / "dst.nc").read_bytes() == b"hello"


def test_bgcironforcing_process(tmp_path):
    (tmp_path / "ocnice").mkdir()
    depth, ny, nx = 103, 60, 60

    configurator = BGCIronForcingConfigurator(
        case_session_id="abc123", case_grid_name="test"
    )
    configurator.set_output_param("MARBL_FESEDFLUX_FILE", "fesed.nc")
    configurator.set_output_param("MARBL_FEVENTFLUX_FILE", "fevent.nc")
    configurator.set_output_param("MARBL_FESEDFLUXRED_FILE", "fesedred.nc")

    ctx = _make_ctx(tmp_path)
    ctx.grid = SimpleNamespace(nx=nx, ny=ny)

    configurator.process(ctx)

    assert (tmp_path / "ocnice" / "fesed.nc").exists()
    assert (tmp_path / "ocnice" / "fevent.nc").exists()
    for path, main_var in [
        (tmp_path / "ocnice" / "fesed.nc", "FESEDFLUXIN"),
        (tmp_path / "ocnice" / "fevent.nc", "FESEDFLUXIN"),
    ]:
        ds = xr.open_dataset(path)

        assert ds.sizes["DEPTH"] == depth
        assert ds.sizes["ny"] == ny
        assert ds.sizes["nx"] == nx
        assert ds.sizes["DEPTH_EDGES"] == depth + 1

        assert main_var in ds
        assert "DEPTH" in ds
        assert "DEPTH_EDGES" in ds
        assert "KMT" in ds
        assert "TAREA" in ds

        assert ds[main_var].shape == (depth, ny, nx)

        ds.close()


@pytest.mark.slow
def test_bgcrivernutrients_process(tmp_path, is_glade_file_system, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid
    mapping_file = "/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama/GLOFAS_to_panama1_map_r20_f40_nnsm.nc"
    output_file = tmp_path / "riv_flux.nc"

    configurator = BGCRiverNutrientsConfigurator(
        global_river_nutrients_filepath="/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/rof/river_nutrients/river_nutrients.GNEWS_GNM.glofas.20250916.64bit.nc",
        case_session_id="abc123",
        case_grid_name="panama1",
        calendar=NOLEAP,
    )
    configurator.set_output_param("RIV_FLUX_FILE", "riv_flux.nc")

    ctx = _make_ctx(tmp_path, output_path=tmp_path)
    ctx.grid = grid
    ctx.config = {"runoff": {"outputs": {"ROF2OCN_LIQ_RMAPNAME": mapping_file}}}

    configurator.process(ctx)

    assert output_file.exists()
    mapping_ds = xr.open_dataset(mapping_file)
    riv_file = xr.open_dataset(output_file)
    assert riv_file.sizes["ny"] == mapping_ds.sizes["nj_b"]
    assert riv_file.sizes["nx"] == mapping_ds.sizes["ni_b"]
    required_vars = [
        "din_riv_flux",
        "dip_riv_flux",
        "don_riv_flux",
        "dsi_riv_flux",
        "dic_riv_flux",
        "alk_riv_flux",
        "doc_riv_flux",
    ]

    for v in required_vars:
        assert v in riv_file
        assert riv_file[v].dims == ("time", "ny", "nx")
        assert riv_file[v].attrs["units"] == "mmol/cm^2/s"


# =============================================================================
# Fast mocked test for BGCRiverNutrientsConfigurator.process (avoids --runslow)
# =============================================================================


def _make_fake_global_river_nutrients(nx_src=6, ny_src=5, nt=3):
    """Build a dataset that looks like river_nutrients.GNEWS_GNM.glofas.*.nc."""
    import numpy as np
    import cftime

    rng = np.random.default_rng(0)
    lon_1d = np.linspace(-180.0, 179.0, nx_src)
    lat_1d = np.linspace(-89.0, 89.0, ny_src)
    # Use cftime DatetimeNoLeap so downstream cftime.date2num works.
    time = np.array([cftime.DatetimeNoLeap(2000 + i, 1, 1) for i in range(nt)])

    flux_vars = [
        "din_riv_flux",
        "dip_riv_flux",
        "don_riv_flux",
        "dsi_riv_flux",
        "dic_riv_flux",
        "alk_riv_flux",
        "doc_riv_flux",
    ]
    data_vars = {
        v: (("time", "lat", "lon"), rng.random((nt, ny_src, nx_src)).astype("f4"))
        for v in flux_vars
    }
    # Extra vars that get dropped later
    data_vars.update(
        {
            "LAT": (("lat",), lat_1d),
            "LON": (("lon",), lon_1d),
            "xc": (("lat", "lon"), rng.random((ny_src, nx_src))),
            "xv": (("lat", "lon"), rng.random((ny_src, nx_src))),
            "yc": (("lat", "lon"), rng.random((ny_src, nx_src))),
            "yv": (("lat", "lon"), rng.random((ny_src, nx_src))),
            "area": (("lat", "lon"), rng.random((ny_src, nx_src))),
        }
    )
    ds = xr.Dataset(
        data_vars,
        coords={"lat": lat_1d, "lon": lon_1d, "time": time},
    )
    return ds


def test_bgcrivernutrients_process_mocked(tmp_path, monkeypatch):
    """Fast test of BGCRiverNutrientsConfigurator.process with xe.Regridder mocked out.

    The regridder is replaced by a passthrough callable that returns a dataset
    with the same variables regridded onto a small (ny, nx) target grid, which
    is all that process() requires downstream.
    """
    import numpy as np

    # ---- Build source dataset on disk ----
    src_path = tmp_path / "global_river_nutrients.nc"
    src_ds = _make_fake_global_river_nutrients()
    src_ds.to_netcdf(src_path)

    # ---- Build a small target ocn grid (mock with tlon/tlat DataArrays) ----
    ny_tgt, nx_tgt = 3, 4
    tlon = xr.DataArray(
        np.broadcast_to(np.linspace(0.0, 10.0, nx_tgt), (ny_tgt, nx_tgt)).copy(),
        dims=("ny", "nx"),
    )
    tlat = xr.DataArray(
        np.broadcast_to(
            np.linspace(20.0, 25.0, ny_tgt)[:, None], (ny_tgt, nx_tgt)
        ).copy(),
        dims=("ny", "nx"),
    )
    ocn_grid = MagicMock()
    ocn_grid.tlon = tlon
    ocn_grid.tlat = tlat

    # ---- Mock xe.Regridder so it returns a (ny, nx)-shaped dataset ----
    def _fake_regridder_call(ds):
        nt = ds.sizes.get("time", 3)
        new_data_vars = {}
        for v in ds.data_vars:
            if "time" in ds[v].dims:
                new_data_vars[v] = (
                    ("time", "ny", "nx"),
                    np.ones((nt, ny_tgt, nx_tgt), dtype="f4"),
                )
            else:
                # non-time-varying (LAT, LON, xc, xv, yc, yv, area, etc.)
                new_data_vars[v] = (
                    ("ny", "nx"),
                    np.ones((ny_tgt, nx_tgt), dtype="f4"),
                )
        return xr.Dataset(
            new_data_vars,
            coords={"time": ds["time"].values},
        )

    fake_regridder_instance = MagicMock(side_effect=_fake_regridder_call)
    fake_Regridder = MagicMock(return_value=fake_regridder_instance)
    monkeypatch.setattr("CrocoDash.forcing.bgc.xe.Regridder", fake_Regridder)

    # ---- Run ----
    out_path = tmp_path / "riv_flux.nc"
    configurator = BGCRiverNutrientsConfigurator(
        global_river_nutrients_filepath=str(src_path),
        case_session_id="abc123",
        case_grid_name="test",
        calendar=NOLEAP,
    )
    configurator.set_output_param("RIV_FLUX_FILE", "riv_flux.nc")

    ctx = _make_ctx(tmp_path, output_path=tmp_path)
    ctx.grid = ocn_grid
    ctx.config = {
        "runoff": {"outputs": {"ROF2OCN_LIQ_RMAPNAME": str(tmp_path / "map.nc")}}
    }

    configurator.process(ctx)

    # ---- Assert ----
    assert out_path.exists()
    fake_Regridder.assert_called_once()
    fake_regridder_instance.assert_called_once()

    out = xr.open_dataset(out_path)
    required = [
        "din_riv_flux",
        "dip_riv_flux",
        "don_riv_flux",
        "dsi_riv_flux",
        "dic_riv_flux",
        "alk_riv_flux",
        "doc_riv_flux",
    ]
    for v in required:
        assert v in out
        assert out[v].attrs["units"] == "mmol/cm^2/s"
    # The dropped vars should NOT be present
    for dropped in ["LAT", "LON", "xc", "xv", "yc", "yv", "area"]:
        assert dropped not in out
    # lat/lon from the target grid replaced the source lat/lon
    assert "lat" in out.coords or "lat" in out.data_vars
    assert "lon" in out.coords or "lon" in out.data_vars
    out.close()
