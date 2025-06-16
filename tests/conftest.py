import pytest
import pathlib

# # Add these lines to run CESM tests
import os

os.environ["CESMROOT"] = "/home/manishrv/CROCESM"
os.environ["CIME_MACHINE"] = "ubuntu-latest"

# Dynamically discover all fixtures in fixtures directories
fixtures_dir = pathlib.Path(__file__).parent / "fixtures"
pytest_plugins = [
    f"tests.fixtures.{f.stem}"
    for f in fixtures_dir.glob("*.py")
    if f.stem != "__init__"
]


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
