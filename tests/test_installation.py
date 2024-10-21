import crocodileregionalruckus as crr
from crocodileregionalruckus import grid_gen
from crocodileregionalruckus.rm6 import regional_mom6 as rm6
import pytest


def test_crr_import(tmp_path):
    """
    This test confirms we can import crr driver, and generate a crr_driver object which includes grid_gen, regional_mom6, and regional_casegen objects.
    """

    crr_driver_obj = crr.driver.crr_driver()
    crr_driver_obj.setup_directories(mom_input_dir=tmp_path/"mom_input", mom_run_dir=tmp_path/"mom_run")
    assert True

def test_rm6_import():
    """
    This test confirms we can import rm6, and can call the functions inside
    """
    
    empty_expt_obj = rm6.experiment.create_empty()
    assert empty_expt_obj is not None

def test_grid_gen_import():
    """
    This test confirms we can import crr driver, and generate a crr_driver object which includes grid_gen, regional_mom6, and regional_casegen objects.
    """

    grid_gen_obj = grid_gen.GridGen()
    assert grid_gen_obj is not None