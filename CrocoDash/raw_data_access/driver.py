"""
Functions to query the data access tables and validate data, as well as request all four segments
"""

from . import config as tb
from .utils import setup_logger
from typing import Callable, Dict
import importlib
import inspect
import os
import shutil
from pathlib import Path
import tempfile
import xarray as xr
from CrocoDash.grid import Grid

logger = setup_logger(__name__)


class ProductFunctionRegistry:
    """Singleton Class Dynamically loads product functions, validates them, and allows easy execution."""

    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(ProductFunctionRegistry, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        self.functions: Dict[str, Dict[str, Callable]] = (
            {}
        )  # {product: {function_name: function}}
        self._loaded_functions = False
        self.products_df, self.functions_df = tb.load_tables()

    def add_product_config(self, product_name: str, product_info: str | Path | dict):
        return tb.add_product_config(product_name, product_info)
    def load_product_config(self, product_name: str):
        """Load configuration files."""
        return tb.load_product_config(product_name)

    def load_functions(self):
        """Reads the registry tables, dynamically imports functions, and verifies them."""
        if self._loaded_functions:
            logger.info(
                "Functions have already been loaded. To reload, set self._loaded_functions to False"
            )
            return
        for _, row in self.functions_df.iterrows():
            product, submodule, func_name = (
                row.Product_Name.upper(),
                row.Submodule,
                row.Function_Name,
            )
            try:
                module = importlib.import_module(
                    "." + submodule, package="CrocoDash.raw_data_access.datasets"
                )
                func = getattr(module, func_name)

                # Store function reference
                if product not in self.functions:
                    self.functions[product] = {}
                self.functions[product][func_name] = func

            except (ModuleNotFoundError, AttributeError) as e:
                logger.debug(f"Skipping {product}.{func_name}: {e}")
        self._loaded_functions = True

    def list_importable_functions(self, product: str):
        """Lists available functions for a given product."""
        product = product.upper()
        if product in self.functions:
            logger.info(f"\nAvailable functions for {product}:")
            for func_name in self.functions[product]:
                logger.info(f"  - {func_name}")
        else:
            logger.info(f"No functions found for {product}.")

    def validate_function(self, product: str, func_name: str):
        """Runs a quick validation of the function (ensures it runs and returns expected output)."""
        try:
            func = self.functions[product][func_name]
        except KeyError as e:
            logger.error(
                f"Function {func_name} not found for product {product}. Error: {e}"
            )
            return False
        sig = inspect.signature(func)
        temp_dir = Path(tempfile.mkdtemp())
        test_file_name = "test_file.nc"
        test_args = [
            ["2000-01-01", "2000-01-02"],
            30,
            30.1,
            -70.1,
            -70,
            temp_dir,
            test_file_name,
        ]
        if len(sig.parameters) < len(test_args):
            logger.error(
                f"Error: {func_name}: Requires at least {len(test_args)} parameters for dates, corners, and file paths."
            )
            return False
        try:
            res = func(*test_args)
        except Exception as e:
            logger.error(f"Error running function: {e}")
            return False
        try:
            if tb.category_of_product(product) == "forcing":
                if tb.type_of_function(product, func_name) != "SCRIPT":
                    assert any(temp_dir.glob("*.nc")), f"No .nc files found in {temp_dir}"
                else:
                    assert os.path.exists(Path(temp_dir) / os.path.basename(res))
                    
            else:
                logger.error(
                    "Category of product is not supported by the validation function"
                )
                return False
        except AssertionError as e:
            logger.error(f"Checked return result failed: {e}")
            return False
        shutil.rmtree(temp_dir)
        return True

    def verify_data_sufficiency(self, collected_products: list):
        """
        Check if collected_products are sufficient to run the regional model.
        `collected_products` should be a list of products.
        """
        required_categories = set(["bathymetry", "forcing"])

        collected_categories = set(
            self.products_df[self.products_df["Product_Name"].isin(collected_products)][
                "Data_Category"
            ]
        )

        missing_categories = required_categories - collected_categories
        if missing_categories:
            return False, missing_categories
        return True, []


def get_rectangular_segment_info(hgrid: xr.Dataset | Grid):
    """
    This function finds the required segment queries from the hgrid and calls the functions
    """
    if type(hgrid) == Grid:
        hgrid = hgrid.supergrid
        hgrid.x = xr.DataArray(hgrid.x, dims=["nyp", "nxp"])
        hgrid.y = xr.DataArray(hgrid.y, dims=["nyp", "nxp"])
    init_result = {
        "lon_min": float(hgrid.x.min()),
        "lon_max": float(hgrid.x.max()),
        "lat_min": float(hgrid.y.min()),
        "lat_max": float(hgrid.y.max()),
    }
    east_result = {
        "lon_min": float(hgrid.x.isel(nxp=-1).min()),
        "lon_max": float(hgrid.x.isel(nxp=-1).max()),
        "lat_min": float(hgrid.y.isel(nxp=-1).min()),
        "lat_max": float(hgrid.y.isel(nxp=-1).max()),
    }
    west_result = {
        "lon_min": float(hgrid.x.isel(nxp=0).min()),
        "lon_max": float(hgrid.x.isel(nxp=0).max()),
        "lat_min": float(hgrid.y.isel(nxp=0).min()),
        "lat_max": float(hgrid.y.isel(nxp=0).max()),
    }
    south_result = {
        "lon_min": float(hgrid.x.isel(nyp=0).min()),
        "lon_max": float(hgrid.x.isel(nyp=0).max()),
        "lat_min": float(hgrid.y.isel(nyp=0).min()),
        "lat_max": float(hgrid.y.isel(nyp=0).max()),
    }
    north_result = {
        "lon_min": float(hgrid.x.isel(nyp=-1).min()),
        "lon_max": float(hgrid.x.isel(nyp=-1).max()),
        "lat_min": float(hgrid.y.isel(nyp=-1).min()),
        "lat_max": float(hgrid.y.isel(nyp=-1).max()),
    }
    return {
        "east": east_result,
        "west": west_result,
        "north": north_result,
        "south": south_result,
        "ic": init_result,
    }
