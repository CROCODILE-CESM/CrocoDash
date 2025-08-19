"""
Test the modules that are minimal, and primarily just need to be checked for connection
"""


def test_grid_connection():
    from CrocoDash.grid import Grid

    assert Grid is not None


def test_topo_connection():
    from CrocoDash.topo import Topo

    assert Topo is not None


def test_topo_editor_connection():
    from CrocoDash.topo_editor import TopoEditor

    assert TopoEditor is not None


def test_vgrid_connection():
    from CrocoDash.vgrid import VGrid

    assert VGrid is not None

@pytest.mark.slow
def test_topo_interpolate_from_file(
    get_rect_grid_and_empty_topo, get_dummy_bathymetry_data, tmp_path
):

    # Basically test that the function is able to connect to the RM6 function it wraps, with a simple smoke test, with a check that the depth was filled
    bathymetry_data = get_dummy_bathymetry_data
    bathymetry_path = tmp_path / "bathymetry.nc"
    bathymetry_data.to_netcdf(bathymetry_path)
    rect_grid, topo = get_rect_grid_and_empty_topo
    topo.interpolate_from_file(
        file_path=bathymetry_path,
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation",
    )

    assert topo.depth is not None
