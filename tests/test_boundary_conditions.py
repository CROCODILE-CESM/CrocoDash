import pytest
from crocodileregionalruckus import boundary_conditions as bc
from crocodileregionalruckus import grid_gen as gg
import os
from pathlib import Path


def test_setup_initial_condition():
    bc_obj = bc.BoundaryConditions(delete_temp_storage=False)
    grid_obj = gg.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    resolution = 0.05
    hgrid = grid_obj.create_rectangular_hgrid(
        longitude_extent, latitude_extent, resolution
    )
    vgrid = grid_obj.create_vgrid(75, 10, 5)
    glorys_path = os.path.join(
        "/", "glade", "derecho", "scratch", "manishrv", "inputs_rm6_hawaii", "glorys"
    )
    # Define a mapping from the GLORYS variables and dimensions to the MOM6 ones
    ocean_varnames = {
        "time": "time",
        "yh": "latitude",
        "xh": "longitude",
        "zl": "depth",
        "eta": "zos",
        "u": "uo",
        "v": "vo",
        "tracers": {"salt": "so", "temp": "thetao"},
    }
    bc_obj.setup_initial_condition(
        hgrid, vgrid, Path(glorys_path) / "ic_unprocessed.nc", ocean_varnames
    )
    assert bc_obj.temp_storage == ".crr_bcc_temp"


def test_setup_ocean_state_boundaries():
    bc_obj = bc.BoundaryConditions(delete_temp_storage=False)
    grid_obj = gg.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    resolution = 0.05
    hgrid = grid_obj.create_rectangular_hgrid(
        longitude_extent, latitude_extent, resolution
    )
    vgrid = grid_obj.create_vgrid(75, 10, 5)
    glorys_path = os.path.join(
        "/", "glade", "derecho", "scratch", "manishrv", "inputs_rm6_hawaii", "glorys"
    )
    # Define a mapping from the GLORYS variables and dimensions to the MOM6 ones
    ocean_varnames = {
        "time": "time",
        "y": "latitude",
        "x": "longitude",
        "zl": "depth",
        "eta": "zos",
        "u": "uo",
        "v": "vo",
        "tracers": {"salt": "so", "temp": "thetao"},
    }
    bc_obj.setup_ocean_state_boundaries(
        hgrid,
        vgrid,
        "2020-01-01",
        glorys_path,
        ocean_varnames,
        boundaries=["south", "north", "west", "east"],
    )
    assert bc_obj.temp_storage == ".crr_bcc_temp"


def test_setup_boundary_tides():

    bc_obj = bc.BoundaryConditions(delete_temp_storage=False)
    grid_obj = gg.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    resolution = 0.05
    tidal_constituents = ["M2"]
    hgrid = grid_obj.create_rectangular_hgrid(
        longitude_extent, latitude_extent, resolution
    )

    bc_obj.setup_boundary_tides(
        hgrid,
        "2020-01-01",
        tidal_constituents,
        Path("/glade/u/home/manishrv/manish_scratch_symlink/inputs_rm6/tidal_data"),
        Path("tpxo9.v1.nc"),
    )
