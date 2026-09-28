"""
This module (logging) contains logging functions that are used across the CrocoDash package.
"""

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


def quiet_visualcasegen_info():
    """Hide visualCaseGen's INFO messages (stage changes, widget updates).

    These narrate visualCaseGen's GUI wizard, which a CrocoDash user never
    sees. visualCaseGen names its loggers with leading whitespace ("\tstage",
    "  csp_solver") and nothing else does, so only those are raised to
    WARNING: its warnings still show, and so does every other logger.

    Meant to be called once, right after visualCaseGen is imported (all its
    loggers exist by then). A logger whose level is already set is left
    alone, and any level can still be changed afterwards.
    """
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if (
            name[:1].isspace()
            and isinstance(logger, logging.Logger)
            and logger.level == logging.NOTSET
        ):
            logger.setLevel(logging.WARNING)
