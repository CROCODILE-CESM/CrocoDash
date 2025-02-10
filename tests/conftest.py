import pytest
import socket
import os
from pathlib import Path
from CrocoDash.rm6 import regional_mom6 as rm6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.case import Case
import xarray as xr
import numpy as np


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="Run slow tests"
    )


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


@pytest.fixture
def get_CrocoDash_case(tmp_path, gen_grid_topo_vgrid, is_github_actions, is_glade):
    # Set Grid Info
    grid, topo, vgrid = gen_grid_topo_vgrid

    # Find CESM Root
    cesmroot = os.getenv("CESMROOT")
    assert cesmroot is not None, "CESMROOT environment variable is not set"

    # Set some defaults
    caseroot, inputdir = tmp_path / "case", tmp_path / "inputdir"
    project_num = "NCGD0011"
    override = True
    inittime = "1850"
    datm_mode = "JRA"
    datm_grid_name = "TL319"
    ninst = 2
    if is_github_actions:
        machine = "ubuntu-latest"
    elif is_glade:
        machine = "derecho"
    else:
        machine = None

    # Setup Case
    case = Case(
        cesmroot=cesmroot,
        caseroot=caseroot,
        inputdir=inputdir,
        ocn_grid=grid,
        ocn_vgrid=vgrid,
        ocn_topo=topo,
        project=project_num,
        override=override,
        machine=machine,
        inittime=inittime,
        datm_mode=datm_mode,
        datm_grid_name=datm_grid_name,
        ninst=ninst,
    )
    return case


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


@pytest.fixture()
def is_github_actions():
    return os.getenv("GITHUB_ACTIONS") == "true"


@pytest.fixture(scope="session")
def get_cesm_root_path(is_glade):
    cesmroot = os.getenv("CESMROOT")
    if cesmroot is None and is_glade:
        cesmroot = "/glade/u/home/manishrv/work/installs/CROCESM_beta04"
    return cesmroot


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
