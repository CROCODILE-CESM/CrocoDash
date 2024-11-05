import crocodileregionalruckus as crr


def test_import():
    assert True


def test_driver_class_init():
    driver = crr.driver.CRRDriver()
    assert driver is not None
