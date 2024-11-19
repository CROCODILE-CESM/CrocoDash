import CrocoDash as cd


def test_import():
    assert True


def test_driver_class_init():
    driver = cd.driver.CrocoDashDriver()
    assert driver is not None
