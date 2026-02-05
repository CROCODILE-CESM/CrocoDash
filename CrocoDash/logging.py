"""
This module (logging) contains logging functions that are used across the CrocoDash package.
"""

import os
import logging
import sys


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
