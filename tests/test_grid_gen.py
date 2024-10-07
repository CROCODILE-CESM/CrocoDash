import crocodileregionalruckus as crr
from crocodileregionalruckus import grid_gen
import pytest
import os
from pathlib import Path
import numpy as np
import xarray as xr
@pytest.fixture(scope="module")
def dummy_tidal_data():
    nx = 2160
    ny = 1081
    nc = 15
    nct = 4

    # Define tidal constituents
    con_list = [
        "m2  ",
        "s2  ",
        "n2  ",
        "k2  ",
        "k1  ",
        "o1  ",
        "p1  ",
        "q1  ",
        "mm  ",
        "mf  ",
        "m4  ",
        "mn4 ",
        "ms4 ",
        "2n2 ",
        "s1  ",
    ]
    con_data = np.array([list(con) for con in con_list], dtype="S1")

    # Generate random data for the variables
    lon_z_data = np.tile(np.linspace(-180, 180, nx), (ny, 1)).T
    lat_z_data = np.tile(np.linspace(-90, 90, ny), (nx, 1))
    ha_data = np.random.rand(nc, nx, ny)
    hp_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    hRe_data = np.random.rand(nc, nx, ny)
    hIm_data = np.random.rand(nc, nx, ny)

    # Create the xarray dataset
    ds_h = xr.Dataset(
        {
            "con": (["nc", "nct"], con_data),
            "lon_z": (["nx", "ny"], lon_z_data),
            "lat_z": (["nx", "ny"], lat_z_data),
            "ha": (["nc", "nx", "ny"], ha_data),
            "hp": (["nc", "nx", "ny"], hp_data),
            "hRe": (["nc", "nx", "ny"], hRe_data),
            "hIm": (["nc", "nx", "ny"], hIm_data),
        },
        coords={
            "nc": np.arange(nc),
            "nct": np.arange(nct),
            "nx": np.arange(nx),
            "ny": np.arange(ny),
        },
        attrs={
            "type": "Fake OTIS tidal elevation file",
            "title": "Fake TPXO9.v1 2018 tidal elevation file",
        },
    )

    # Generate random data for the variables for u_tpxo9.v1
    lon_u_data = (
        np.random.rand(nx, ny) * 360 - 180
    )  # Random longitudes between -180 and 180
    lat_u_data = (
        np.random.rand(nx, ny) * 180 - 90
    )  # Random latitudes between -90 and 90
    lon_v_data = (
        np.random.rand(nx, ny) * 360 - 180
    )  # Random longitudes between -180 and 180
    lat_v_data = (
        np.random.rand(nx, ny) * 180 - 90
    )  # Random latitudes between -90 and 90
    Ua_data = np.random.rand(nc, nx, ny)
    ua_data = np.random.rand(nc, nx, ny)
    up_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    Va_data = np.random.rand(nc, nx, ny)
    va_data = np.random.rand(nc, nx, ny)
    vp_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    URe_data = np.random.rand(nc, nx, ny)
    UIm_data = np.random.rand(nc, nx, ny)
    VRe_data = np.random.rand(nc, nx, ny)
    VIm_data = np.random.rand(nc, nx, ny)

    # Create the xarray dataset for u_tpxo9.v1
    ds_u = xr.Dataset(
        {
            "con": (["nc", "nct"], con_data),
            "lon_u": (["nx", "ny"], lon_u_data),
            "lat_u": (["nx", "ny"], lat_u_data),
            "lon_v": (["nx", "ny"], lon_v_data),
            "lat_v": (["nx", "ny"], lat_v_data),
            "Ua": (["nc", "nx", "ny"], Ua_data),
            "ua": (["nc", "nx", "ny"], ua_data),
            "up": (["nc", "nx", "ny"], up_data),
            "Va": (["nc", "nx", "ny"], Va_data),
            "va": (["nc", "nx", "ny"], va_data),
            "vp": (["nc", "nx", "ny"], vp_data),
            "URe": (["nc", "nx", "ny"], URe_data),
            "UIm": (["nc", "nx", "ny"], UIm_data),
            "VRe": (["nc", "nx", "ny"], VRe_data),
            "VIm": (["nc", "nx", "ny"], VIm_data),
        },
        coords={
            "nc": np.arange(nc),
            "nct": np.arange(nct),
            "nx": np.arange(nx),
            "ny": np.arange(ny),
        },
        attrs={
            "type": "Fake OTIS tidal transport file",
            "title": "Fake TPXO9.v1 2018 WE/SN transports/currents file",
        },
    )

    return ds_h, ds_u


def test_rm6_gen_hgrid():
    # Define the grid
    grid_obj = grid_gen.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    resolution = 0.05
    grid = grid_obj.create_rectangular_hgrid(longitude_extent, latitude_extent, resolution)
    assert grid is not None
    assert grid_obj.hgrid is not None

def test_fred_subset_hgrid():
    # Define the grid
    grid_obj = grid_gen.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    resolution = 0.05
    grid = grid_obj.subset_global_hgrid(longitude_extent, latitude_extent, resolution)
    assert grid is not None
    assert grid_obj.hgrid is not None

def test_all_funcs_with_rectangle_grid(dummy_tidal_data):
    expt_name = "testing"
    latitude_extent = [24, 27]
    longitude_extent = [207, 209]

    date_range = ["2005-01-01 00:00:00", "2005-02-01 00:00:00"]

    ## Place where all your input files go
    input_dir = Path(
        os.path.join(
            expt_name,
            "inputs",
        )
    )

    ## Directory where you'll run the experiment from
    run_dir = Path(
        os.path.join(
            expt_name,
            "run_files",
        )
    )
    for path in (run_dir, input_dir):
        os.makedirs(str(path), exist_ok=True)

    ## User-1st, test if we can even read the angled nc files.
    crr_driver_obj = crr.driver.crr_driver(
        longitude_extent=longitude_extent,
        latitude_extent=latitude_extent,
        date_range=date_range,
        resolution=0.05,
        number_vertical_layers=75,
        layer_thickness_ratio=10,
        depth=4500,
        minimum_depth=5,
        mom_run_dir=run_dir,
        mom_input_dir=input_dir,
        toolpath_dir="",
    )
    crr_driver_obj.setup_directories(run_dir, input_dir)



    hgrid = crr_driver_obj.grid_gen.create_rectangular_hgrid(crr_driver_obj.og_mom6.longitude_extent, crr_driver_obj.og_mom6.latitude_extent, crr_driver_obj.og_mom6.resolution)
    vgrid = crr_driver_obj.grid_gen.create_vgrid(crr_driver_obj.og_mom6.number_vertical_layers, crr_driver_obj.og_mom6.layer_thickness_ratio, crr_driver_obj.og_mom6.depth)

    
    crr_driver_obj.wrap_rm6_setup_bathymetry(
        "/glade/u/home/manishrv/manish_scratch_symlink/inputs_rm6/gebco/GEBCO_2024.nc",
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation",
        hgrid = hgrid
    )

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
    glorys_path = os.path.join("/","glade","derecho","scratch","manishrv","inputs_rm6_hawaii","glorys" )
    # Set up the initial condition
    crr_driver_obj.wrap_rm6_setup_initial_condition(
        Path(glorys_path)
        / "ic_unprocessed.nc",  # directory where the unprocessed initial condition is stored, as defined earlier
        ocean_varnames,
        arakawa_grid="A",
        hgrid = hgrid,
        vgrid = vgrid
    )

    # Set up the four boundary conditions. Remember that in the glorys_path, we have four boundary files names north_unprocessed.nc etc.
    crr_driver_obj.wrap_rm6_setup_ocean_state_boundaries(
        glorys_path,
        ocean_varnames,
        boundaries=["south", "north", "west", "east"],
        arakawa_grid="A",
        hgrid = hgrid
    )
    ds_h, ds_u = dummy_tidal_data
    dump_files_dir = Path(crr_driver_obj.mom_input_dir / "tides")
    os.makedirs(dump_files_dir, exist_ok=True)
    ds_h.to_netcdf(dump_files_dir / "h_fake_tidal_data.nc")
    ds_u.to_netcdf(dump_files_dir / "u_fake_tidal_data.nc")
    crr_driver_obj.wrap_rm6_setup_tides(dump_files_dir, "fake_tidal_data.nc", hgrid = hgrid)
    crr_driver_obj.wrap_rm6_setup_run_directory(
    surface_forcing="jra", with_tides_rectangular=True, overwrite=True,hgrid = hgrid,vgrid = vgrid, premade_rundir_path_arg=Path("/glade/u/home/manishrv/documents/nwa12_0.1/regional_mom_workflows/crr/crocodileregionalruckus/rm6_dir/demos/premade_run_directories")
    )
