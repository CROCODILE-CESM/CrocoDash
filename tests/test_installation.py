from CrocoDash.case import Case
from CrocoDash.rm6 import regional_mom6 as rm6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid


def test_import():
    """
    This test confirms we can import cd submodules
    """

    assert Case is not None
    assert Grid is not None
    assert Topo is not None
    assert VGrid is not None


def test_rm6_import():
    """
    This test confirms we can import rm6, and can call the functions inside
    """

    empty_expt_obj = rm6.experiment.create_empty()
    assert empty_expt_obj is not None
