"""
Functions to query the data access tables and validate data 
"""

import pandas as pd
from pathlib import Path


TABLES_DIR = (
    Path(__file__).parent / "tables"
)  # Adjust this to wherever your tables are stored


def load_tables():
    """Load data tables from CSV files."""

    products_df = pd.read_csv(f"{TABLES_DIR}/data_product_registry.csv")
    functions_df = pd.read_csv(f"{TABLES_DIR}/data_access_registry.csv")
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


def verify_data_sufficiency(collected_products: list):
    """
    Check if collected_products are sufficient to run the regional model.
    `collected_products` should be a list of products.
    """
    products_df, _ = load_tables()
    required_categories = set(["bathymetry", "forcing"])

    collected_categories = set(
        products_df[products_df["Product_Name"].isin(collected_products)][
            "Data_Category"
        ]
    )

    missing_categories = required_categories - collected_categories
    if missing_categories:
        return False, missing_categories
    return True, []
