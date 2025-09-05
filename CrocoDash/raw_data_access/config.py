from pathlib import Path
import pandas as pd
import json

CONFIG_DIR = (
    Path(__file__).parent / "config"
)  # Adjust this to wherever your config is stored


def load_product_config(product_name: str):
    """Load configuration files."""
    with open(f"{CONFIG_DIR}/{product_name}.json", "r") as f:
        data = json.load(f)  # Use `json.load()` for files
    return data


def load_tables():
    """Load data tables from CSV files."""

    products_df = pd.read_csv(f"{CONFIG_DIR}/data_product_registry.csv")
    functions_df = pd.read_csv(f"{CONFIG_DIR}/data_access_registry.csv")
    return products_df, functions_df


def list_products():
    """Return a list of available data products."""
    products_df, _ = load_tables()
    return products_df["Product_Name"].tolist()


def list_functions(product_name):
    """Return functions available for a given data product."""
    products_df, functions_df = load_tables()

    if product_name not in products_df["Product_Name"].values:
        raise ValueError(f"Product '{product_name}' not found.")

    return functions_df[functions_df["Product_Name"] == product_name][
        "Function_Name"
    ].tolist()


def product_exists(product_name):
    """Check if a product exists."""
    products_df, _ = load_tables()
    return product_name in products_df["Product_Name"].values


def function_exists(product_name, function_name):
    """Check if a function exists for a given product."""
    _, functions_df = load_tables()
    return (
        (functions_df["Product_Name"] == product_name)
        & (functions_df["Function_Name"] == function_name)
    ).any()


def type_of_function(product_name, function_name):
    """Returns the type of function, python or script, the function is"""
    _, functions_df = load_tables()
    if function_exists(product_name, function_name):
        return functions_df[
            (functions_df["Product_Name"] == product_name)
            & (functions_df["Function_Name"] == function_name)
        ]["Access_Type"].values[0]

    else:
        raise ValueError("Invalid product & function name combination")


def category_of_product(product_name):
    """Returns the type of function, python or script, the function is"""
    products_df, _ = load_tables()
    if product_exists(product_name):
        return products_df[(products_df["Product_Name"] == product_name)][
            "Data_Category"
        ].values[0]

    else:
        raise ValueError("Invalid product name combination")
