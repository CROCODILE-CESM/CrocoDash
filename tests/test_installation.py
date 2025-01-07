import CrocoDash as cd
from CrocoDash import grid_gen
from CrocoDash.regional_casegen import cesm_tools as rcg_ct
from CrocoDash.rm6 import regional_mom6 as rm6
import pytest


def test_cd_import(tmp_path):
    """
    This test confirms we can import cd driver, and generate a cd_driver object which includes grid_gen, regional_mom6, and regional_casegen objects.
    """

    cd_driver_obj = cd.driver.CrocoDashDriver()
    assert cd_driver_obj is not None


def test_rm6_import():
    """
    This test confirms we can import rm6, and can call the functions inside
    """

    empty_expt_obj = rm6.experiment.create_empty()
    assert empty_expt_obj is not None


def test_grid_gen_import():
    """
    This test confirms we can import grid_gen, and can call the functions inside
    """

    grid_gen_obj = grid_gen.GridGen()
    assert grid_gen_obj is not None


def test_rcg_import():
    """
    This test confirms we can import rcg, and can call the functions inside
    """

    rcg_obj = rcg_ct.RegionalCaseGen()
    assert rcg_obj is not None
