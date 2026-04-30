"""
This testing file is for the other processes in extract_forcings. Most do not need much testing because they call other packages (which should ideally test correctness themselves) (I mean I'm probably writing those tests but still)
"""

import pytest
from CrocoDash.extract_forcings import runoff, tides, bgc, chlorophyll as chl
import xarray as xr
from unittest.mock import Mock, patch


@patch("mom6_forge.mapping.gen_rof_maps", autospec=True)
def test_process_runoff(mock_runoff, is_glade_file_system, tmp_path):
    runoff.generate_rof_ocn_map(
        rof_grid_name="GLOFAS",
        rof_esmf_mesh_filepath="/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/rof/glofas/dis24/GLOFAS_esmf_mesh_v4.nc",
        ocn_mesh_filepath="/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama/ESMF_mesh_panama1_352fd1.nc",
        inputdir=tmp_path,
        grid_name="test",
        rmax=20,
        fold=40,
    )

    assert mock_runoff.called


@patch("regional_mom6.regional_mom6.experiment.setup_boundary_tides", autospec=True)
def test_process_tides(mock_tides, tmp_path, gen_grid_topo_vgrid, dummy_tidal_data):
    grid, topo, vgrid = gen_grid_topo_vgrid
    elev, vel = dummy_tidal_data
    grid.write_supergrid(tmp_path / "grid.nc")
    vgrid.write(tmp_path / "vgrid.nc")
    (tmp_path / "ocnice").mkdir()
    tides.process_tides(
        ocn_topo=topo,
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        tidal_constituents=["M2"],
        boundaries=["east"],
        tpxo_elevation_filepath=elev,
        tpxo_velocity_filepath=vel,
    )

    assert mock_tides.called


@patch("mom6_forge.chl.interpolate_and_fill_seawifs", autospec=True)
def test_process_chl(mock_chl, is_glade_file_system, tmp_path, gen_grid_topo_vgrid):

    grid, topo, vgrid = gen_grid_topo_vgrid
    chl.process_chl(
        ocn_grid=grid,
        ocn_topo=topo,
        inputdir=tmp_path,
        chl_processed_filepath="/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/chl/data/SeaWIFS.L3m.MC.CHL.chlor_a.0.25deg.nc",
        output_filepath=tmp_path / "chl.nc",
    )

    assert mock_chl.called


def test_bgcironforcing(tmp_path):
    (tmp_path / "ocnice").mkdir()
    depth, ny, nx = 103, 60, 60
    bgc.process_bgc_iron_forcing(
        nx=60,
        ny=60,
        MARBL_FESEDFLUX_FILE="fesed.nc",
        MARBL_FEVENTFLUX_FILE="fevent.nc",
        inputdir=tmp_path,
    )

    assert (tmp_path / "ocnice" / "fesed.nc").exists()
    assert (tmp_path / "ocnice" / "fevent.nc").exists()
    for path, main_var in [
        (tmp_path / "ocnice" / "fesed.nc", "FESEDFLUXIN"),
        (tmp_path / "ocnice" / "fevent.nc", "FESEDFLUXIN"),
    ]:
        ds = xr.open_dataset(path)

        # --- dimension checks ---
        assert ds.dims["DEPTH"] == depth
        assert ds.dims["ny"] == ny
        assert ds.dims["nx"] == nx
        assert ds.dims["DEPTH_EDGES"] == depth + 1

        # --- variable presence ---
        assert main_var in ds
        assert "DEPTH" in ds
        assert "DEPTH_EDGES" in ds
        assert "KMT" in ds
        assert "TAREA" in ds

        # --- main variable shape ---
        assert ds[main_var].shape == (depth, ny, nx)

        ds.close()


@pytest.mark.slow
def test_bgcrivernutrients(tmp_path, is_glade_file_system, gen_grid_topo_vgrid):

    grid, topo, vgrid = gen_grid_topo_vgrid
    mapping_file = "/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama/GLOFAS_to_panama1_map_r20_f40_nnsm.nc"
    output_file = tmp_path / "riv_flux.nc"
    bgc.process_river_nutrients(
        ocn_grid=grid,
        global_river_nutrients_filepath="/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/rof/river_nutrients/river_nutrients.GNEWS_GNM.glofas.20250916.64bit.nc",
        mapping_file=mapping_file,
        river_nutrients_nnsm_filepath=output_file,
    )
    assert output_file.exists()
    mapping_file = xr.open_dataset(mapping_file)
    riv_file = xr.open_dataset(output_file)
    assert riv_file.dims["ny"] == mapping_file.dims["nj_b"]
    assert riv_file.dims["nx"] == mapping_file.dims["ni_b"]
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
# Fast mocked test for process_river_nutrients (avoids --runslow dependency)
# =============================================================================


def _make_fake_global_river_nutrients(nx_src=6, ny_src=5, nt=3):
    """Build a dataset that looks like river_nutrients.GNEWS_GNM.glofas.*.nc."""
    import numpy as np
    import xarray as xr
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


def test_bgcrivernutrients_mocked(tmp_path, monkeypatch):
    """Fast test of process_river_nutrients with xe.Regridder mocked out.

    The regridder is replaced by a passthrough callable that returns a dataset
    with the same variables regridded onto a small (ny, nx) target grid, which
    is all that process_river_nutrients requires downstream.
    """
    import numpy as np
    import xarray as xr
    from unittest.mock import MagicMock
    from CrocoDash.extract_forcings import bgc

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
    monkeypatch.setattr("CrocoDash.extract_forcings.bgc.xe.Regridder", fake_Regridder)

    # ---- Run ----
    out_path = tmp_path / "riv_flux.nc"
    bgc.process_river_nutrients(
        global_river_nutrients_filepath=str(src_path),
        ocn_grid=ocn_grid,
        mapping_file=str(tmp_path / "map.nc"),
        river_nutrients_nnsm_filepath=str(out_path),
    )

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


# =============================================================================
# Small direct-call tests that cover one-liner branches
# =============================================================================


def test_process_bgc_ic_copies_file(tmp_path):
    """process_bgc_ic is a thin shutil.copy wrapper; confirm it copies bytes."""
    src = tmp_path / "src.nc"
    src.write_bytes(b"hello")
    dst = tmp_path / "out" / "dst.nc"
    dst.parent.mkdir()
    bgc.process_bgc_ic(str(src), str(dst))
    assert dst.read_bytes() == b"hello"


@patch("mom6_forge.mapping.gen_rof_maps", autospec=True)
@patch("mom6_forge.mapping.get_smoothed_map_filepath")
def test_generate_rof_ocn_map_reuses_existing(
    mock_get_filepath, mock_gen_maps, tmp_path
):
    """If the smoothed-map file already exists, gen_rof_maps must not be called."""
    existing = tmp_path / "mapping" / "EXISTING_map.nc"
    existing.parent.mkdir(parents=True, exist_ok=False)
    existing.write_text("x")
    mock_get_filepath.return_value = existing

    runoff.generate_rof_ocn_map(
        rof_grid_name="GLOFAS",
        rof_esmf_mesh_filepath="/fake/rof_mesh.nc",
        ocn_mesh_filepath="/fake/ocn_mesh.nc",
        inputdir=tmp_path,
        grid_name="fake_grid",
        rmax=20,
        fold=40,
    )
    # The "already exists, reusing it" branch should be taken.
    mock_gen_maps.assert_not_called()
