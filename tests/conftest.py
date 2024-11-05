import pytest
import socket
import os
from pathlib import Path


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


@pytest.fixture(scope="session")
def get_dummy_data_folder():
    return Path(os.path.join(os.path.abspath(os.path.dirname(__file__)), "dummy_data"))
