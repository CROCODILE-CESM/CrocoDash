"""
This GridGen tester doesn't include the floater functions or RM6 wrapped functions... but it does test the basic functionality of the GridGen class.
"""

import crocodileregionalruckus as crr
from crocodileregionalruckus import grid_gen
import pytest
import xarray as xr
import os
import numpy as np


def test_grid_gen_init_basic():
    """
    This test confirms we can import crr.grid_gen, and generate a GridGen object.
    """

    grid_gen_obj = grid_gen.GridGen()
    assert grid_gen_obj is not None


def test_grid_gen_properties(get_dummy_data_folder):
    """
    This test confirms if the getters and setters work for grid_gen
    """
    hgrid_path = get_dummy_data_folder / "light_rm6_input" / "hgrid.nc"
    vgrid_path = get_dummy_data_folder / "light_rm6_input" / "vcoord.nc"
    bathymetry_path = get_dummy_data_folder / "light_rm6_input" / "bathymetry.nc"
    grid_gen_obj = grid_gen.GridGen()
    og_hgrid = xr.open_dataset(hgrid_path)
    og_vgrid = xr.open_dataset(vgrid_path)
    og_topo = xr.open_dataset(bathymetry_path)

    ## Set the Properties
    grid_gen_obj.hgrid = og_hgrid
    grid_gen_obj.vgrid = og_vgrid
    grid_gen_obj.topo = og_topo

    ## Check if in temp_storage
    assert os.path.exists(grid_gen_obj._hgrid_path)
    assert os.path.exists(grid_gen_obj._vgrid_path)
    assert os.path.exists(grid_gen_obj._topo_path)

    ## Access the datasets again
    assert og_hgrid.x == grid_gen_obj.hgrid
    assert np.array_equal(og_vgrid.zl, grid_gen_obj.vgrid.zl)
    assert np.array_equal(og_topo.x, grid_gen_obj.topo.x)


def test_subset_global_hgrid():
    return


def test_subset_global_topo():
    return


def test_verify_and_modify_read_vgrid():
    return


def test_mask_disconnected_ocean_areas():
    return


@pytest.mark.slow
def test_rm6_functions_run():
    return
