import logging
import sys


def fill_template(template_path, output_path, **kwargs):
    """
    Reads a template file, fills it with the provided arguments,
    and writes the filled content to a new file.

    Args:
        template_path (str): Path to the template file.
        output_path (str): Path to save the filled template.
        **kwargs: Key-value pairs for substitution in the template.
    """
    # Read the template file
    with open(template_path, "r") as template_file:
        template_content = template_file.read()

    # Substitute placeholders with provided arguments
    filled_content = template_content.format(**kwargs)

    # Write the filled content to the output file
    with open(output_path, "w") as output_file:
        output_file.write(filled_content)

    print(f"Filled PBS script written to: {output_path}")


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
