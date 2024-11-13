import crocodile_dashboard as cd
from crocodile_dashboard import grid_gen
import pytest
import os
from pathlib import Path
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt


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
    grid = grid_obj.create_rectangular_hgrid(
        longitude_extent, latitude_extent, resolution
    )
    assert grid is not None
    assert grid_obj.hgrid is not None


@pytest.mark.usefixtures("check_glade_exists")
def test_fred_subset_hgrid():
    # Define the grid
    grid_obj = grid_gen.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    grid = grid_obj.subset_global_hgrid(longitude_extent, latitude_extent)
    assert grid is not None
    assert grid_obj.hgrid is not None


def test_fred_subset_topo():
    # Define the grid
    assert True


@pytest.mark.usefixtures("check_glade_exists")
def test_rm6_mask_unwanted_ocean(tmp_path):
    # Define the grid
    grid_obj = grid_gen.GridGen(delete_temp_storage=False)
    latitude_extent = [9, 12]
    longitude_extent = [-79, -77]
    for i in range(2):
        longitude_extent[i] = (longitude_extent[i] + 360) % 360
    # hgrid = xr.open_dataset("/glade/u/home/manishrv/documents/nwa12_0.1/.cd_temp/hgrid.nc")
    # topo = xr.open_dataset("/glade/u/home/manishrv/documents/nwa12_0.1/.cd_temp/topo.nc")
    resolution = 0.05
    hgrid = grid_obj.create_rectangular_hgrid(
        longitude_extent, latitude_extent, resolution
    )
    bathymetry_path = (
        "/glade/u/home/manishrv/manish_scratch_symlink/inputs_rm6/gebco/GEBCO_2024.nc"
    )
    topo = grid_obj.setup_bathymetry(
        input_dir=Path(tmp_path),
        longitude_extent=longitude_extent,
        latitude_extent=latitude_extent,
        minimum_depth=5,
        bathymetry_path=bathymetry_path,
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation",
        hgrid=hgrid,
    )
    topo = grid_obj.mask_disconnected_ocean_areas(
        hgrid=hgrid,
        topo=grid_obj.topo.depth[0],
        name_x_dim="x",
        name_y_dim="y",
        lat_pt=10,
        lon_pt=-78,
    )
    # plt.figure(dpi=250)
    # plt.imshow(topo.depth, origin="lower", interpolation="nearest")
    # plt.savefig(os.path.join("topo_after_masking.png"))
