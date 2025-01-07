"""
This module (test_utils) tests the utility functions in the utils module. For lowkey utils, we'll just use smoke tests.
"""

import CrocoDash as crr
from CrocoDash import utils
import pytest
import xarray as xr


def test_utils_smoke(dummy_netcdf_data, tmp_path):

    logger = utils.setup_logger("test_utils")
    assert logger is not None

    # Test export_dataset
    utils.export_dataset(dummy_netcdf_data, tmp_path / "hgrid_test.nc")
