from CrocoDash.data_access import rectangular as rt
from CrocoDash.data_access import glorys as gl
import xarray as xr

def test_get_rectangular_boundary_conditions(get_rect_grid, tmp_path):
    dates = ["2000-01-01", "2000-01-05"]
    grid = get_rect_grid
    grid.write_supergrid(tmp_path/"test.nc")
    hgrid = xr.open_dataset(tmp_path/"test.nc")
    assert rt.get_rectangular_boundary_conditions(dates,hgrid,gl.get_glorys_data_from_rda,{} )