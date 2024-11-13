import crocodile_dashboard as crr


def test_import():
    assert True


def test_driver_class_init():
    driver = crr.driver.crr_driver()
    assert driver is not None
