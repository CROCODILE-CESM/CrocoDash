import pytest
import socket
import os
from pathlib import Path
from CrocoDash.rm6 import regional_mom6 as rm6


# Fixture to provide the temp folder and a parameter name
@pytest.fixture
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
def check_glade_exists():
    if not is_glade_file_system():
        pytest.skip(reason="Skipping test: Not running on the Glade file system.")


import xarray as xr
import numpy as np


@pytest.fixture(scope="session")
def dummy_netcdf_data():
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
