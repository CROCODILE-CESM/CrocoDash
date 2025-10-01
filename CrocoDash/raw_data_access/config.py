from pathlib import Path
import pandas as pd
import json

CONFIG_DIR = (
    Path(__file__).parent / "config"
)  # Adjust this to wherever your config is stored


def add_product_config(product_name: str, product_info: str | Path | dict):
    """Add Product Config file if not already created"""
    product_name = product_name.lower()
    output_path = CONFIG_DIR / (product_name + ".json")
    if output_path.exists():
        raise ValueError(f"Product config already exists in {output_path}. Please delete this to replace it.")
    else:

        if isinstance(product_info, (str, Path)):
            with open(product_info, "r") as f:
                product_info = json.load(f)
        elif product_info == None:
            raise ValueError(f"No product info provided but product information does not exist in {output_path}")
            return
        # Validate, must have the keys time, xh, yh, u, v, ssh, z_dim or zl, and a subdict called tracers with the fields salt, temp
        required_keys = {"time", "xh", "yh", "u", "v", "ssh", "zl", "u_lat_name","u_lon_name","v_lat_name","v_lon_name","z_unit_conversion"}
        tracer_keys = {"salt", "temp"}

        missing = []

        # Check top-level keys
        for key in required_keys:
            if key not in product_info:
                missing.append(key)

        # Check tracers subdict
        if "tracers" not in product_info or not isinstance(product_info["tracers"], dict):
            missing.append("tracers (dict with at least salt, temp)")
        else:
            for key in tracer_keys:
                if key not in product_info["tracers"]:
                    missing.append(f"tracers.{key}")

        if missing:
            raise ValueError(f"Product dict is missing required keys: {', '.join(missing)}")

        # Write out
        with open(output_path, "w") as f:
            json.dump(product_info, f, indent=4)

def load_product_config(product_name: str):
    """Load configuration files."""
    product_name = product_name.lower()
    try:
        with open(f"{CONFIG_DIR}/{product_name}.json", "r") as f:
            data = json.load(f)  # Use `json.load()` for files
            return data
    except:
        raise ValueError(f"Product Information not found in {CONFIG_DIR}/{product_name}")


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
