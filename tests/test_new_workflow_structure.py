import crocodileregionalruckus as crr


def test_import():
    assert True

def test_driver_class_init():
    driver = crr.driver.crr_driver()
    assert driver is not None


def test_grid_generation():
    driver = crr.driver.crr_driver()
    driver.setup_directories()
    driver.generate_grids()
def test_full_workflow():
    driver = crr.driver.crr_driver()
    driver.setup_directories()
    driver.generate_grids()
    driver.generate_boundary_conditions()
    driver.setup_MOM_files()
    driver.setup_CESM_case()