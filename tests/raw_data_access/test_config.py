from CrocoDash.raw_data_access import tables as tb
import pytest


def test_load_tables():
    products, functions = tb.load_tables()
    assert "GLORYS" in products["Product_Name"].values
    assert "GLORYS" in functions["Product_Name"].values


def test_load_varnames_config():
    config = tb.load_varnames_config()
    assert "GLORYS" in config.keys()


def test_list_products():
    products = tb.list_products()
    assert "GLORYS" in products


def test_list_functions():
    functions = tb.list_functions("GLORYS")
    assert "get_glorys_data_from_rda" in functions


def test_product_exists():
    assert tb.product_exists("GLORYS") == True
    assert tb.product_exists("BLOOP") == False


def test_function_exists():
    assert tb.function_exists("GLORYS", "get_glorys_data_from_rda") == True
    assert tb.function_exists("GLORYS", "BLOOP") == False


def test_type_of_function():
    assert tb.type_of_function("GLORYS", "get_glorys_data_from_rda") == "PYTHON"
    with pytest.raises(ValueError):
        assert tb.type_of_function("GLORYS", "get_sdfsdfsdfglorys_data")


def test_category_of_product():
    assert tb.category_of_product("GLORYS") == "forcing"
    with pytest.raises(ValueError):
        assert tb.category_of_product("sdgfsdfsdgsdfgsgsd")
