from CrocoDash.data_access import query_validate as qv


def test_load_tables():
    products, functions = qv.load_tables()
    assert "GLORYS" in products["Product_Name"].values
    assert "GLORYS" in functions["Product_Name"].values

def test_list_products():
    products = qv.list_products()
    assert "GLORYS" in products

def test_list_functions():
    functions = qv.list_functions("GLORYS")
    assert "get_glorys_data_from_rda" in functions

def test_product_exists():
    assert qv.product_exists("GLORYS") == True
    assert qv.product_exists("BLOOP") == False

def test_function_exists():
    assert qv.function_exists("GLORYS","get_glorys_data_from_rda") == True
    assert qv.function_exists("GLORYS","BLOOP") == False

def test_verify_data_sufficiency():
    sufficient, missing = qv.verify_data_sufficiency(["GLORYS","GEBCO"])
    assert sufficient == True
    sufficient, missing = qv.verify_data_sufficiency(["GLORYS","TPXO"])
    assert sufficient == False
    assert len(missing) == 1
    assert list(missing)[0] == "bathymetry"