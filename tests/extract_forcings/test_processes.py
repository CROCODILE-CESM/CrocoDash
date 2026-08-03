"""
This testing file is for the other processes in extract_forcings. Most do not need much testing because they call other packages (which should ideally test correctness themselves) (I mean I'm probably writing those tests but still)
"""

from pathlib import Path

import pytest
from CrocoDash.extract_forcings import runoff, tides, bgc, chlorophyll as chl, cice, ww3
from CrocoDash.raw_data_access.base import WW3ForcingProduct, accessmethod, GREGORIAN
import numpy as np
import pandas as pd
import xarray as xr
from unittest.mock import Mock, patch

# Reference files for the cice_restart product -- same as
# tests/raw_data_access/test_cice.py. Duplicated here (rather than imported)
# since each test file in this suite is self-contained.
_CICE_GRID_PATH = "/glade/campaign/cesm/community/omwg/grids/tx2_3v3_grid.nc"
_CICE_RESTART_PATH = (
    "/glade/u/home/dbailey/"
    "b.e30_alpha09b.B1850C_MTso.ne30_t233_wgx3.360.cice.r.0201-01-01-00000.nc"
)


def _skip_if_cice_reference_files_missing():
    if not Path(_CICE_GRID_PATH).exists() or not Path(_CICE_RESTART_PATH).exists():
        pytest.skip(
            "Reference tx2_3v3 grid or CICE restart file not available on this "
            "filesystem."
        )


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


def test_process_cice_ic_not_implemented(tmp_path, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid

    with pytest.raises(NotImplementedError):
        cice.process_cice_ic(
            ocn_grid=grid,
            inputdir=tmp_path,
            date_range=("2020-01-01 00:00:00", "2020-01-01 06:00:00"),
            cice_product_name="GLORYS",
            cice_function_name="get_glorys_data_from_rda",
        )


def test_cice_boundary_lines_geometry(gen_grid_topo_vgrid):
    """North/east boundaries get their own T-row/column's U-point exactly on
    the true domain edge; south/east get it one cell inside instead -- a
    direct consequence of CICE's NW-corner B-grid convention applied to
    grid.qlon/qlat's indexing (see _cice_boundary_lines's docstring)."""
    grid, topo, vgrid = gen_grid_topo_vgrid

    south = cice._cice_boundary_lines(grid, "south")
    north = cice._cice_boundary_lines(grid, "north")
    west = cice._cice_boundary_lines(grid, "west")
    east = cice._cice_boundary_lines(grid, "east")

    nx, ny = grid.tlon.shape[1], grid.tlon.shape[0]
    for lines, n in [(south, nx), (north, nx), (west, ny), (east, ny)]:
        for key in ("t_lon", "t_lat", "u_lon", "u_lat"):
            assert lines[key].shape == (n,)

    # Grid is an unrotated rectangle, so each true edge is a constant
    # lon/lat -- safe to read off a single corner point.
    true_south_edge_lat = float(grid.qlat.values[0, 0])
    true_north_edge_lat = float(grid.qlat.values[-1, 0])
    true_west_edge_lon = float(grid.qlon.values[0, 0])
    true_east_edge_lon = float(grid.qlon.values[0, -1])

    # North/west: boundary-most row/column's own U-point sits exactly on
    # the true edge.
    assert np.allclose(north["u_lat"], true_north_edge_lat)
    assert np.allclose(west["u_lon"], true_west_edge_lon)

    # South/east: one cell inside the true edge, not on it.
    assert np.all(south["u_lat"] > true_south_edge_lat)
    assert np.all(east["u_lon"] < true_east_edge_lon)

    # Velocity/stress line always sits strictly between the true edge and
    # the tracer line for the "interior" boundaries (south/east) -- half a
    # cell further in than tracers.
    assert np.all(south["u_lat"] > south["t_lat"])
    assert np.all(east["u_lon"] < east["t_lon"])

    # For the "aligned" boundaries (north/west), it's the tracer line that
    # sits strictly between the true edge and the U-line instead.
    assert np.all(north["t_lat"] < north["u_lat"])
    assert np.all(west["t_lon"] > west["u_lon"])


def test_cice_boundary_lines_unknown_boundary_raises(gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid
    with pytest.raises(ValueError):
        cice._cice_boundary_lines(grid, "northeast")


def test_process_cice_obc_produces_output(
    skip_if_not_glade, tmp_path, gen_grid_topo_vgrid
):
    """process_cice_obc runs the full GET -> chunk -> REGRID -> MERGE engine
    for real against the reference restart + grid files -- confirms the
    wiring end-to-end, not just that it reaches a known gap."""
    _skip_if_cice_reference_files_missing()
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")

    cice.process_cice_obc(
        hgrid_path=tmp_path / "grid.nc",
        inputdir=tmp_path,
        boundaries=["west", "east"],
        date_range=("2020-01-01", "2020-01-01"),
        function_args={
            "restart_path": _CICE_RESTART_PATH,
            "grid_path": _CICE_GRID_PATH,
        },
    )

    west = xr.open_dataset(tmp_path / "ocnice" / "cice_forcing_obc_segment_001.nc")
    east = xr.open_dataset(tmp_path / "ocnice" / "cice_forcing_obc_segment_002.nc")

    for ds, n in [(west, grid.tlat.shape[0]), (east, grid.tlat.shape[0])]:
        assert ds.sizes["boundary_point"] == n
        assert ds.sizes["time"] == 1
        assert "aicen" in ds and ds["aicen"].dims == ("time", "ncat", "boundary_point")
        assert "uvel" in ds and ds["uvel"].dims == ("time", "boundary_point")
        # No ice expected at this (Panama-region) test grid's location.
        assert float(ds["aicen"].sum()) == 0.0


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


def test_process_ww3_obc(tmp_path, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    # obc.py's shared engine tracks GET/REGRID chunks at whole-day
    # granularity (filenames and coverage checks are date-only), so -- unlike
    # the old standalone implementation -- date_range here can't carry
    # sub-day precision.
    ww3.process_ww3_obc(
        hgrid_path=str(hgrid_path),
        inputdir=tmp_path,
        boundaries=["west", "east"],
        date_range=("2020-01-01", "2020-01-02"),
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
        # hourly, spanning the full requested run window inclusive:
        # 2020-01-01T00:00 through 2020-01-02T00:00 = 25 points
        assert ds1.dims["time"] == 25
        assert ds2.dims["time"] == 25
        # each station gets a distinct, identifiable constant value (point i:
        # 1e-3*i) so the station a boundary cell's data came from can be
        # checked directly, at every timestep
        assert float(ds1["efth"].isel(time=0).max()) == pytest.approx(1e-3)
        assert float(ds2["efth"].isel(time=0).max()) == pytest.approx(2e-3)
        assert float(ds1["efth"].isel(time=24).max()) == pytest.approx(1e-3)
        assert float(ds2["efth"].isel(time=24).max()) == pytest.approx(2e-3)
    finally:
        ds1.close()
        ds2.close()


def _make_synthetic_era5_window(n_stations=3):
    """Synthetic dataset matching the real decoded ERA5 shape (see
    raw_data_access.datasets.era5.decode_era5_spectra_grib) -- a regular
    (time, latitude, longitude, frequency, direction) grid -- so the real
    regrid logic can be exercised without any network/GRIB dependency. Uses
    a single latitude row (n_stations longitude columns), so each (lat, lon)
    point maps 1:1 onto a station index k after _extract_all_stations's
    stack, with a distinct, checkable efth value (100 + k) confirming no
    station gets reduced/averaged with another.
    """
    time = pd.date_range("2020-01-01", periods=4, freq="6h")
    freq = np.array([0.05, 0.1, 0.15])
    direction = np.array([0.0, 120.0, 240.0])
    lons = np.linspace(-170.0, -160.0, n_stations)
    lats = np.array([68.5])
    efth = np.zeros((len(time), 1, n_stations, len(freq), len(direction)))
    for k in range(n_stations):
        efth[:, 0, k, :, :] = 100.0 + k
    return xr.Dataset(
        {
            "wave_spectra": (
                ("time", "latitude", "longitude", "frequency", "direction"),
                efth,
            )
        },
        coords={
            "time": time.values,
            "latitude": lats,
            "longitude": lons,
            "frequency": freq,
            "direction": direction,
        },
    )


def test_extract_all_stations_keeps_every_point():
    ds = _make_synthetic_era5_window(n_stations=3)
    lons, lats, freq, direction, efth = ww3._extract_all_stations(ds)

    assert list(lons) == list(ds["longitude"].values)
    assert list(lats) == [68.5, 68.5, 68.5]
    assert list(freq) == list(ds["frequency"].values)
    assert list(direction) == list(ds["direction"].values)
    assert efth.shape == (3, 4, 3, 3)  # (station, time, frequency, direction)
    for k in range(3):
        assert np.all(efth[k] == 100.0 + k)


def test_extract_all_stations_shape_mismatch_raises():
    # Missing the "direction" dim entirely -- should trigger the check.
    bad = xr.Dataset(
        {
            "wave_spectra": (
                ("time", "latitude", "longitude", "frequency"),
                np.ones((4, 1, 3, 3)),
            )
        },
        coords={
            "time": pd.date_range("2020-01-01", periods=4, freq="6h").values,
            "latitude": [68.5],
            "longitude": [1.0, 2.0, 3.0],
            "frequency": [0.05, 0.1, 0.15],
        },
    )
    with pytest.raises(ValueError, match="direction"):
        ww3._extract_all_stations(bad)


def test_regrid_chunk_era5_writes_all_stations(tmp_path):
    ds = _make_synthetic_era5_window(n_stations=3)

    ww3._regrid_chunk_era5(
        ds=ds,
        hgrid=None,
        boundary="west",
        seg_id=3,
        outfolder=tmp_path,
        dataset_varnames={},
        start_date="2020-01-01",
        regridders=None,
    )

    out = xr.open_dataset(tmp_path / "forcing_obc_segment_003.nc")
    try:
        assert out.sizes["station"] == 3
        for k in range(3):
            assert np.all(out["efth"].isel(station=k).values == 100.0 + k)
        assert list(out["station_lon"].values) == list(ds["longitude"].values)
        assert list(out["station_lat"].values) == [68.5, 68.5, 68.5]
    finally:
        out.close()


class _FakeERA5Spectra(WW3ForcingProduct):
    """Test-only stand-in for era5.ERA5_WAVE_SPECTRA -- writes a synthetic
    dataset already in the real decoded ERA5 shape (see
    _make_synthetic_era5_window), instead of hitting CDS/GRIB, so
    process_ww3_obc's real (non-placeholder) path can be exercised
    end-to-end without network/credentials. Auto-registers on import via
    BaseProduct.__init_subclass__, same as test_base_registry.py's
    DummyProduct/DummyForcing fixtures."""

    product_name = "test_fake_era5_spectra"
    description = "Fake multi-station ERA5-shaped spectra for testing."
    link = "n/a"
    time_var_name = "time"
    time_units = None
    calendar = GREGORIAN

    @accessmethod
    def get_fake_spectra(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="fake_era5.nc",
        variables=None,
    ):
        start, end = pd.to_datetime(dates[0]), pd.to_datetime(dates[1])
        time = pd.date_range(start, end, freq="6h")
        freq = np.array([0.05, 0.1, 0.15])
        direction = np.array([0.0, 120.0, 240.0])
        n_stations = 3
        lons = np.linspace(lon_min, lon_max, n_stations)
        lats = np.array([(lat_min + lat_max) / 2])
        efth = np.zeros((len(time), 1, n_stations, len(freq), len(direction)))
        for k in range(n_stations):
            efth[:, 0, k, :, :] = 100.0 + k

        ds = xr.Dataset(
            {
                "wave_spectra": (
                    ("time", "latitude", "longitude", "frequency", "direction"),
                    efth,
                )
            },
            coords={
                "time": time.values,
                "latitude": lats,
                "longitude": lons,
                "frequency": freq,
                "direction": direction,
            },
        )
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        path = output_folder / output_filename
        ds.to_netcdf(path)
        return path


def test_process_ww3_obc_era5_path_multi_station(tmp_path, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    ww3.process_ww3_obc(
        hgrid_path=str(hgrid_path),
        inputdir=tmp_path,
        boundaries=["west", "east"],
        date_range=("2020-01-01", "2020-01-02"),
        ww3_obc_product_name="test_fake_era5_spectra",
        ww3_obc_function_name="get_fake_spectra",
    )

    ocnice = tmp_path / "ocnice"
    # 2 boundaries x 3 real stations each = 6 total, not 2.
    spec_lines = (ocnice / "spec.list").read_text().splitlines()
    assert spec_lines == [f"ww3.point{i}_spec.nc" for i in range(1, 7)]

    nml_contents = (ocnice / "ww3_bounc.nml").read_text()
    assert "BOUND%INTERP               = 2" in nml_contents

    for i, expected_value in zip(range(1, 7), [100.0, 101.0, 102.0] * 2):
        ds = xr.open_dataset(ocnice / f"ww3.point{i}_spec.nc", decode_times=False)
        try:
            assert np.all(ds["efth"].values == expected_value)
        finally:
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
