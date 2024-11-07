"""
This module (test_utils) tests the utility functions in the utils module. For lowkey utils, we'll just use smoke tests.
"""

import crocodileregionalruckus as crr
from crocodileregionalruckus import utils
import pytest
import xarray as xr


def test_utils_smoke(get_dummy_data_folder, tmp_path):

    logger = utils.setup_logger("test_utils")
    assert logger is not None

    # Test export_dataset
    ds = xr.open_dataset(get_dummy_data_folder / "light_rm6_input" / "hgrid.nc")
    utils.export_dataset(ds, tmp_path / "hgrid_test.nc")
