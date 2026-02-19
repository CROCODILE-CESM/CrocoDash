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


def test_grid_creator_connection():
    from CrocoDash.grid_creator import GridCreator

    assert GridCreator is not None


def test_vgrid_creator_connection():
    from CrocoDash.vgrid_creator import VGridCreator

    assert VGridCreator is not None
