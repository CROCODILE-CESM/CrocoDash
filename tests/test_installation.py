import crocodileregionalruckus as crr
from crocodileregionalruckus.rm6 import regional_mom6 as rm6
import pytest


def test_import(temp_dir):

    crr_driver_obj = crr.driver.crr_driver()
    crr_driver_obj.setup_directories(mom_input_dir=temp_dir+"/mom_input", mom_run_dir=temp_dir+"/mom_run")