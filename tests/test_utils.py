"""
This module (test_utils) tests the utility functions in the utils module. For lowkey utils, we'll just use smoke tests.
"""

from CrocoDash import utils


def test_utils_smoke(get_dummy_bathymetry_data, tmp_path):

    # Test logger
    logger = utils.setup_logger("test_utils")
    assert logger is not None

    # Test export_dataset
    utils.export_dataset(get_dummy_bathymetry_data, tmp_path / "temp_test.nc")
