"""
This testing file is for the other processes in extract_forcings. Most do not need much testing because they call other packages (which should ideally test correctness themselves) (I mean I'm probably writing those tests but still)
"""

import pytest
from CrocoDash.extract_forcings import runoff, tides, bgc, chlorophyll as chl
import xarray as xr
from unittest.mock import Mock, patch


@patch("mom6_bathy.mapping.gen_rof_maps", autospec=True)
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


@patch("mom6_bathy.chl.interpolate_and_fill_seawifs", autospec=True)
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
