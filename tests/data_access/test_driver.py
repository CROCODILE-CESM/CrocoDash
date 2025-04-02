from CrocoDash.raw_data_access import driver as dv
import pytest


@pytest.fixture
def get_ProductFunctionRegistry():
    pfd_obj = dv.ProductFunctionRegistry()
    return pfd_obj


def test_init_ProductFunctionRegistry():
    pfd_obj = dv.ProductFunctionRegistry()
    assert pfd_obj


def test_load_functions_ProductFunctionRegistry(get_ProductFunctionRegistry):
    pfd_obj = get_ProductFunctionRegistry
    pfd_obj.load_functions()
    assert len(pfd_obj.functions.keys()) > 0
    assert len(pfd_obj.functions["GLORYS"].keys()) > 0


def test_validate_function(get_ProductFunctionRegistry):
    pfd_obj = get_ProductFunctionRegistry
    pfd_obj.load_functions()
    assert pfd_obj.validate_function("GLORYS", "get_glorys_data_script_for_cli")
    assert not pfd_obj.validate_function("GLORYS", "get_glorys_data_frm_BROKE")


def test_verify_data_sufficiency(get_ProductFunctionRegistry):
    pfd_obj = get_ProductFunctionRegistry
    sufficient, missing = pfd_obj.verify_data_sufficiency(["GLORYS", "GEBCO"])
    assert sufficient == True
    sufficient, missing = pfd_obj.verify_data_sufficiency(["GLORYS", "TPXO"])
    assert sufficient == False
    assert len(missing) == 1
    assert list(missing)[0] == "bathymetry"


def test_get_rectangular_segment_info(get_rect_grid):
    grid = get_rect_grid
    res = dv.get_rectangular_segment_info(grid)
    assert "east" in res.keys()
    assert "west" in res.keys()
    assert "north" in res.keys()
    assert "south" in res.keys()
    assert "lat_min" in res["east"].keys()
