# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import sys
import os
import subprocess
from pathlib import Path
sys.path.insert(0, os.path.abspath("../.."))


output_path_module = Path("_static/module_diagram.svg")
output_path_workflow = Path("_static/workflow_diagram.svg")
if not output_path_module.exists():
    subprocess.run(["bash", "diagrams/module_diagram.sh"], check=True)
if not output_path_workflow.exists():
    subprocess.run(["python", "diagrams/workflow_visualize.py"], check=True)

# Run the Bash script

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "CrocoDash"
copyright = "2024, CROCODILE"
author = "CROCODILE"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon","nbsphinx"]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
nbsphinx_execute="never"
html_logo = "_static/logo.png"