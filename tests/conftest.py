import pytest
import socket
import os
from pathlib import Path
from CrocoDash.rm6 import regional_mom6 as rm6


# Fixture to provide the temp folder and a parameter name
@pytest.fixture
def get_rect_grid():
    grid = Grid(
        resolution=0.1,
        xstart=278.0,
        lenx=4.0,
        ystart=7.0,
        leny=3.0,
        name="panama1",
    )
    return grid


@pytest.fixture
def get_rect_grid_and_empty_topo(get_rect_grid):
    topo = Topo(
        grid=get_rect_grid,
        min_depth=9.5,
    )
    return get_rect_grid, topo


@pytest.fixture
def get_rect_grid_and_topo(get_rect_grid):
    topo = Topo(
        grid=get_rect_grid,
        min_depth=9.5,
    )
    topo.depth = 10
    return get_rect_grid, topo


@pytest.fixture
def gen_grid_topo_vgrid(get_rect_grid_and_topo):
    grid, topo = get_rect_grid_and_topo
    vgrid = VGrid.hyperbolic(nk=75, depth=topo.max_depth, ratio=20.0)
    return grid, topo, vgrid


@pytest.fixture
def get_dummy_bathymetry_data():
    latitude_extent = [2, 10]
    longitude_extent = [260, 280]
    bathymetry = np.random.random((100, 100)) * (-100)
    bathymetry = xr.DataArray(
        bathymetry,
        dims=["lat", "lon"],
        coords={
            "lat": np.linspace(latitude_extent[0] - 5, latitude_extent[1] + 5, 100),
            "lon": np.linspace(longitude_extent[0] - 5, longitude_extent[1] + 5, 100),
        },
    )
    bathymetry.name = "elevation"
    return bathymetry


@pytest.fixture(scope="session")
def setup_sample_rm6_expt(tmp_path):
    expt = rm6.experiment(
        longitude_extent=[10, 12],
        latitude_extent=[10, 12],
        date_range=["2000-01-01 00:00:00", "2000-01-01 00:00:00"],
        resolution=0.05,
        number_vertical_layers=75,
        layer_thickness_ratio=10,
        depth=4500,
        minimum_depth=25,
        mom_run_dir=tmp_path / "light_rm6_run",
        mom_input_dir=tmp_path / "light_rm6_input",
        toolpath_dir=Path(""),
        hgrid_type="even_spacing",
        vgrid_type="hyperbolic_tangent",
        expt_name="test",
    )
    return expt


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="Run slow tests"
    )


def pytest_collection_modifyitems(config, items):
    if not config.option.runslow:
        # Skip slow tests if --runslow is not provided
        skip_slow = pytest.mark.skip(reason="Skipping slow tests by default")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


def is_glade_file_system():
    # Get the hostname
    hostname = socket.gethostname()
    # Check if "derecho" or "casper" is in the hostname and glade exists currently
    is_on_glade_bool = (
        "derecho" in hostname or "casper" in hostname
    ) and os.path.exists("/glade")

    return is_on_glade_bool


@pytest.fixture(scope="session")
def is_glade():
    if not is_glade_file_system():
        pytest.skip(reason="Skipping test: Not running on the Glade file system.")


import xarray as xr
import numpy as np


@pytest.fixture(scope="session")
def dummy_temp_data():
    # Create dummy data
    time = np.arange(10)  # 10 time steps
    lat = np.linspace(-90, 90, 5)  # 5 latitude points
    lon = np.linspace(-180, 180, 5)  # 5 longitude points
    data = np.random.rand(len(time), len(lat), len(lon))  # Random 3D data

    # Create an xarray Dataset
    ds = xr.Dataset(
        {
            "temperature": (["time", "lat", "lon"], data),  # Data variable
        },
        coords={
            "time": time,
            "lat": lat,
            "lon": lon,
        },
        attrs={"description": "Dummy dataset for temperature"},
    )
    return ds


@pytest.fixture(scope="session")
def dummy_tidal_data():
    nx = 100
    ny = 100
    nc = 15
    nct = 4

    # Define tidal constituents
    con_list = [
        "m2  ",
        "s2  ",
        "n2  ",
        "k2  ",
        "k1  ",
        "o1  ",
        "p1  ",
        "q1  ",
        "mm  ",
        "mf  ",
        "m4  ",
        "mn4 ",
        "ms4 ",
        "2n2 ",
        "s1  ",
    ]
    con_data = np.array([list(con) for con in con_list], dtype="S1")

    # Generate random data for the variables
    lon_z_data = np.tile(np.linspace(-180, 180, nx), (ny, 1)).T
    lat_z_data = np.tile(np.linspace(-90, 90, ny), (nx, 1))
    ha_data = np.random.rand(nc, nx, ny)
    hp_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    hRe_data = np.random.rand(nc, nx, ny)
    hIm_data = np.random.rand(nc, nx, ny)

    # Create the xarray dataset
    ds_h = xr.Dataset(
        {
            "con": (["nc", "nct"], con_data),
            "lon_z": (["nx", "ny"], lon_z_data),
            "lat_z": (["nx", "ny"], lat_z_data),
            "ha": (["nc", "nx", "ny"], ha_data),
            "hp": (["nc", "nx", "ny"], hp_data),
            "hRe": (["nc", "nx", "ny"], hRe_data),
            "hIm": (["nc", "nx", "ny"], hIm_data),
        },
        coords={
            "nc": np.arange(nc),
            "nct": np.arange(nct),
            "nx": np.arange(nx),
            "ny": np.arange(ny),
        },
        attrs={
            "type": "Fake OTIS tidal elevation file",
            "title": "Fake TPXO9.v1 2018 tidal elevation file",
        },
    )

    # Generate random data for the variables for u_tpxo9.v1
    lon_u_data = (
        np.random.rand(nx, ny) * 360 - 180
    )  # Random longitudes between -180 and 180
    lat_u_data = (
        np.random.rand(nx, ny) * 180 - 90
    )  # Random latitudes between -90 and 90
    lon_v_data = (
        np.random.rand(nx, ny) * 360 - 180
    )  # Random longitudes between -180 and 180
    lat_v_data = (
        np.random.rand(nx, ny) * 180 - 90
    )  # Random latitudes between -90 and 90
    Ua_data = np.random.rand(nc, nx, ny)
    ua_data = np.random.rand(nc, nx, ny)
    up_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    Va_data = np.random.rand(nc, nx, ny)
    va_data = np.random.rand(nc, nx, ny)
    vp_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    URe_data = np.random.rand(nc, nx, ny)
    UIm_data = np.random.rand(nc, nx, ny)
    VRe_data = np.random.rand(nc, nx, ny)
    VIm_data = np.random.rand(nc, nx, ny)

    # Create the xarray dataset for u_tpxo9.v1
    ds_u = xr.Dataset(
        {
            "con": (["nc", "nct"], con_data),
            "lon_u": (["nx", "ny"], lon_u_data),
            "lat_u": (["nx", "ny"], lat_u_data),
            "lon_v": (["nx", "ny"], lon_v_data),
            "lat_v": (["nx", "ny"], lat_v_data),
            "Ua": (["nc", "nx", "ny"], Ua_data),
            "ua": (["nc", "nx", "ny"], ua_data),
            "up": (["nc", "nx", "ny"], up_data),
            "Va": (["nc", "nx", "ny"], Va_data),
            "va": (["nc", "nx", "ny"], va_data),
            "vp": (["nc", "nx", "ny"], vp_data),
            "URe": (["nc", "nx", "ny"], URe_data),
            "UIm": (["nc", "nx", "ny"], UIm_data),
            "VRe": (["nc", "nx", "ny"], VRe_data),
            "VIm": (["nc", "nx", "ny"], VIm_data),
        },
        coords={
            "nc": np.arange(nc),
            "nct": np.arange(nct),
            "nx": np.arange(nx),
            "ny": np.arange(ny),
        },
        attrs={
            "type": "Fake OTIS tidal transport file",
            "title": "Fake TPXO9.v1 2018 WE/SN transports/currents file",
        },
    )

    return ds_h, ds_u


@pytest.fixture
def dummy_forcing_factory():
    """Factory fixture to create dummy forcing NetCDF datasets with configurable latitudes."""

    def _create_dummy_forcing_dataset(lat_min=30, lat_max=35, lon_min=30, lon_max=35):
        latitude = np.linspace(lat_min, lat_max, 20)
        longitude = np.linspace(lon_min, lon_max, 20)
        depth =np.array([0,1000,2000,3000,4000,5000,6000,7000,8000,9000],dtype=np.float64)
        time = np.arange(32)

        data = {
            "so": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "thetao": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "uo": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "vo": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "zos": (
                ("time", "latitude", "longitude"),
                np.random.rand(32, 20, 20).astype(np.float64),
            ),
        }

        ds = xr.Dataset(
            data,
            coords={
                "depth": depth,
                "latitude": latitude,
                "longitude": longitude,
                "time": time,
            },
        )
        return ds

    return _create_dummy_forcing_dataset
