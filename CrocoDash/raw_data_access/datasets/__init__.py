# CrocoDash/raw_data_access/datasets/__init__.py

import pkgutil
import importlib

def load_all_datasets():
    """
    Dynamically import all modules in this package so that their
    _init_subclass hook run and populate the registry.
    """
    package = __name__
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{package}.{module_name}")