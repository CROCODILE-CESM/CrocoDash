"""
This testing file is for the other processes in extract_forcings. Most do not need much testing because they call other packages (which should ideally test correctness themselves) (I mean I'm probably writing those tests but still)
"""

import pytest
from CrocoDash.extract_forcings import runoff, tides, bgc, chlorophyll as chl, ww3
import numpy as np
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
        MARBL_FESEDFLUXRED_FILE="fesedred.nc",
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


def test_write_ww3_boundary_spectrum_default_time(tmp_path):
    freq = 0.04118 * 1.1 ** np.arange(5)
    direction = np.linspace(0, 360, 4, endpoint=False)
    efth = np.ones((1, 5, 4))
    path = tmp_path / "point_spec.nc"

    ww3.write_ww3_boundary_spectrum(
        path, lat=10.0, lon=200.0, freq=freq, direction=direction, efth=efth
    )

    ds = xr.open_dataset(path, decode_times=False, mask_and_scale=False)
    try:
        assert ds["efth"].shape == (1, 5, 4, 1, 1)
        assert ds["efth"].attrs["_FillValue"] == pytest.approx(-999.9, rel=1e-4)
        assert ds["efth"].attrs["scale_factor"] == pytest.approx(1.0)
        assert ds["efth"].attrs["add_offset"] == pytest.approx(0.0)
        assert ds["time"].attrs["units"] == "seconds since 1990-01-01 00:00:00.0"
        assert ds["time"].attrs["calendar"] == "standard"
        assert float(ds["latitude"].values[0]) == pytest.approx(10.0)
        assert float(ds["longitude"].values[0]) == pytest.approx(200.0)
        # No spurious _FillValue on any coordinate (xarray adds these by
        # default unless explicitly suppressed -- see write_ww3_boundary_spectrum)
        for coord in ("time", "frequency", "direction", "latitude", "longitude"):
            assert "_FillValue" not in ds[coord].attrs
    finally:
        ds.close()


def test_write_ww3_boundary_spectrum_time_units_untouched_by_xarray(tmp_path):
    """
    Regression test for the xarray CF-encoder bug found this session: writing
    a midnight-exact datetime64 time coordinate directly (instead of plain
    float seconds) causes xarray to silently rewrite the "units" attribute,
    dropping the "hh:mm:ss" portion -- which corrupts W3TIMEMD's fixed
    column-position parser in ww3_bounc.
    """
    freq = 0.04118 * 1.1 ** np.arange(3)
    direction = np.linspace(0, 360, 4, endpoint=False)
    time = np.array(["2020-01-01T00:00:00"], dtype="datetime64[ns]")
    efth = np.ones((1, 3, 4))
    path = tmp_path / "point_spec.nc"

    ww3.write_ww3_boundary_spectrum(
        path, lat=0.0, lon=0.0, freq=freq, direction=direction, efth=efth, time=time
    )

    ds = xr.open_dataset(path, decode_times=False, mask_and_scale=False)
    try:
        assert ds["time"].attrs["units"] == "seconds since 1990-01-01 00:00:00.0"
        expected_seconds = (
            time[0] - np.datetime64("1990-01-01T00:00:00", "ns")
        ) / np.timedelta64(1, "s")
        assert float(ds["time"].values[0]) == pytest.approx(expected_seconds)
    finally:
        ds.close()


def test_write_ww3_bounc_nml(tmp_path):
    ww3.write_ww3_bounc_nml(
        tmp_path, spec_list_filename="foo.list", mode="READ", interp=1, verbose=2
    )

    content = (tmp_path / "ww3_bounc.nml").read_text()
    assert "BOUND%MODE                 = 'READ'" in content
    assert "BOUND%INTERP               = 1" in content
    assert "BOUND%VERBOSE              = 2" in content
    assert "BOUND%FILE                 = 'foo.list'" in content


def test_write_spec_list(tmp_path):
    ww3.write_spec_list(tmp_path, ["a_spec.nc", "b_spec.nc"])

    content = (tmp_path / "spec.list").read_text()
    assert content == "a_spec.nc\nb_spec.nc\n"


def test_boundary_points(gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid

    lats, lons = ww3._boundary_points(grid, ["south", "north", "west", "east"])

    assert len(lats) == len(lons) == 4
    # south should sit strictly south of north; west strictly west of east
    assert lats[0] < lats[1]
    assert lons[2] < lons[3]


def test_process_ww3_obc(tmp_path, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid

    ww3.process_ww3_obc(
        ocn_grid=grid,
        inputdir=tmp_path,
        boundaries=["west", "east"],
        date_range=("2020-01-01 00:00:00", "2020-01-01 06:00:00"),
        ww3_obc_product_name="ERA5",
        ww3_obc_function_name="get_era5_2d_spectra",
    )

    ocnice = tmp_path / "ocnice"
    assert (ocnice / "spec.list").exists()
    assert (ocnice / "ww3_bounc.nml").exists()
    assert (ocnice / "ww3.point1_spec.nc").exists()
    assert (ocnice / "ww3.point2_spec.nc").exists()

    assert (ocnice / "spec.list").read_text().splitlines() == [
        "ww3.point1_spec.nc",
        "ww3.point2_spec.nc",
    ]

    # nearest-point mapping (no interpolation between stations), so each
    # boundary cell's forcing traces back to exactly one station
    nml_contents = (ocnice / "ww3_bounc.nml").read_text()
    assert "BOUND%INTERP               = 1" in nml_contents

    ds1 = xr.open_dataset(ocnice / "ww3.point1_spec.nc", decode_times=False)
    ds2 = xr.open_dataset(ocnice / "ww3.point2_spec.nc", decode_times=False)
    try:
        # hourly, spanning the full requested run window inclusive
        assert ds1.dims["time"] == 7
        assert ds2.dims["time"] == 7
        # each station gets a distinct, identifiable constant value (point i:
        # 1e-3*(i+1)) so the station a boundary cell's data came from can be
        # checked directly, at every timestep
        assert float(ds1["efth"].isel(time=0).max()) == pytest.approx(1e-3)
        assert float(ds2["efth"].isel(time=0).max()) == pytest.approx(2e-3)
        assert float(ds1["efth"].isel(time=6).max()) == pytest.approx(1e-3)
        assert float(ds2["efth"].isel(time=6).max()) == pytest.approx(2e-3)
    finally:
        ds1.close()
        ds2.close()


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
