import pytest
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid


@pytest.fixture
def get_rect_grid():
    grid = Grid(
        resolution=0.1,
        xstart=278.0,
        lenx=4.0,
        ystart=7.0,
        leny=3.0,
        name="panama1",
    )
    return grid


@pytest.fixture
def get_rect_grid_and_empty_topo(get_rect_grid):
    topo = Topo(
        grid=get_rect_grid,
        min_depth=9.5,
    )
    return get_rect_grid, topo


@pytest.fixture
def get_rect_grid_and_topo(get_rect_grid):
    topo = Topo(
        grid=get_rect_grid,
        min_depth=9.5,
    )
    topo.depth = 10
    return get_rect_grid, topo


@pytest.fixture
def gen_grid_topo_vgrid(get_rect_grid_and_topo):
    grid, topo = get_rect_grid_and_topo
    vgrid = VGrid.hyperbolic(nk=75, depth=topo.max_depth, ratio=20.0)
    return grid, topo, vgrid
