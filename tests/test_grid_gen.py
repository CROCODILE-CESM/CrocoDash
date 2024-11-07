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


@pytest.mark.usefixtures("check_glade_exists")
def test_subset_global_hgrid(get_dummy_data_folder):
    light_gridgen_path = get_dummy_data_folder / "light_gridgen"

    # Generate a subset of the global hgrid
    grid_gen_obj = grid_gen.GridGen()
    panama_hgrid = grid_gen_obj.subset_global_hgrid([-80, -79], [8, 10])

    # Verify the subset against a produced copy in light_gridgen_path

    assert panama_hgrid == xr.open_dataset(light_gridgen_path / "panama_hgrid.nc")


@pytest.mark.usefixtures("check_glade_exists")
def test_subset_global_topo(get_dummy_data_folder):
    light_gridgen_path = get_dummy_data_folder / "light_gridgen"

    # Generate a subset of the global hgrid
    grid_gen_obj = grid_gen.GridGen()
    panama_topo = grid_gen_obj.subset_global_topo([-80, -79], [8, 10])

    # Verify the subset against a produced copy in light_gridgen_path

    assert panama_topo == xr.open_dataset(light_gridgen_path / "panama_topo.nc")
    return


def test_verify_and_modify_read_vgrid(get_dummy_data_folder):

    # Read three vgrid files - an RM6 Produced one and a NCAR w/ only thickmness and a invalud NCAR one
    light_gridgen_vgrid_path = get_dummy_data_folder / "light_gridgen" / "vgrid_samples"
    vgrid_rm6 = xr.open_dataset(light_gridgen_vgrid_path / "vgrid_rm6.nc")
    vgrid_ncar = xr.open_dataset(light_gridgen_vgrid_path / "vgrid_ncar.nc")
    vgrid_invalid = xr.open_dataset(light_gridgen_vgrid_path / "vgrid_invalid.nc")

    # Verify the vgrids
    grid_gen_obj = grid_gen.GridGen()
    vgrid_rm6_adj = grid_gen_obj.verify_and_modify_read_vgrid(
        light_gridgen_vgrid_path / "vgrid_rm6.nc"
    )
    assert np.array_equal(vgrid_rm6_adj.zl, vgrid_rm6.zl)  # Should be no changes
    with pytest.raises(ValueError):
        vgrid_invalid_adj = grid_gen_obj.verify_and_modify_read_vgrid(
            light_gridgen_vgrid_path / "vgrid_invalid.nc"
        )

    vgrid_ncar_adj = grid_gen_obj.verify_and_modify_read_vgrid(light_gridgen_vgrid_path / "vgrid_ncar.nc")
    correct_ncar_adj = xr.open_dataset(light_gridgen_vgrid_path / "vgrid_ncar_adj.nc")
    assert np.array_equal(vgrid_ncar_adj.dz, vgrid_ncar.dz)  # Should be no changes
    assert np.array_equal(vgrid_ncar_adj.zl, correct_ncar_adj.zl)  # Should be no changes



def test_mask_disconnected_ocean_areas(get_dummy_data_folder):

    # Read an availale topo and hgrid
    light_gridgen_path = get_dummy_data_folder / "light_gridgen"
    panama_topo = xr.open_dataset(light_gridgen_path / "panama_topo.nc")
    panama_hgrid = xr.open_dataset(light_gridgen_path / "panama_hgrid.nc")

    # Choose a point to mask around
    grid_gen_obj = grid_gen.GridGen()
    masked_topo_north = grid_gen_obj.mask_disconnected_ocean_areas(
        panama_hgrid, "x", "y", panama_topo.depth, 9.99, -79.5
    )

    # Verify the masked topo against a produced copy in light_gridgen_path
    assert masked_topo_north == xr.open_dataset(
        light_gridgen_path / "masked_panama_topo_north.nc"
    )


@pytest.mark.usefixtures("check_glade_exists")
@pytest.mark.slow
def test_rm6_functions_smoke(tmp_path):
    grid_gen_obj = grid_gen.GridGen()
    vgrid = grid_gen_obj.create_vgrid(75, 10, 4500, 35)
    hgrid = grid_gen_obj.create_rectangular_hgrid([-80, -79], [8, 10],0.05)
    topo = grid_gen_obj.setup_bathymetry(hgrid,[-80, -79], [8, 10],tmp_path,45,"/glade/u/home/manishrv/manish_scratch_symlink/inputs_rm6/gebco/GEBCO_2024.nc")
    return
