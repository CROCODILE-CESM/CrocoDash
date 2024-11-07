"""
This module (utils) contains utility functions that are used across the crocodileregionalruckus package.
"""

import os
import logging
import sys


def export_dataset(ds, path):
    """
    This function exports an xarray dataset to a netcdf file at the specified path, but deletes the previous netcdf beforehand for safety.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to export.
    path : str
        The path to the netcdf file to export

    Returns
    -------
    None
    """
    if os.path.exists(path):
        os.remove(path)
    ds.to_netcdf(path)
    ds.close()


def setup_logger(name):
    """
    This function sets up a logger format for the package. It attaches logger output to stdout (if a handler doesn't already exist) and formats it in a pretty way!

    Parameters
    ----------
    name : str
        The name of the logger.

    Returns
    -------
    logging.Logger
        The logger

    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.hasHandlers():
        # Create a handler to print to stdout (Jupyter captures stdout)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        # Create a formatter (optional)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s.%(funcName)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(handler)
    return logger
