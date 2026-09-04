# CrocoDash/forcing/__init__.py

import pkgutil
import importlib


def load_all_configurators():
    """
    Dynamically import every module in this package so each configurator
    class's @register decorator runs and populates ForcingConfigRegistry.
    Adding a new forcing type is just adding a new file here -- nothing
    needs to import it by name.
    """
    package = __name__
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{package}.{module_name}")


load_all_configurators()
