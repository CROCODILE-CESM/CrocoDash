# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import sys
import os
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath("../.."))


# output_path_module = Path("_static/module_diagram.svg")
# output_path_workflow = Path("_static/workflow_diagram.svg")
# if not output_path_module.exists():
#     subprocess.run(["bash", "diagrams/module_diagram.sh"], check=True)
# if not output_path_workflow.exists():
#     subprocess.run(["python", "diagrams/workflow_visualize.py"], check=True)
# subprocess.run(["python", "raw_data_access/generate_info.py"], check=True)
# Run the Bash script

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "CrocoDash"
copyright = "2024, CROCODILE"
author = "CROCODILE"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "nbsphinx",
    "myst_parser",
    "sphinxcontrib.mermaid",
]

# Let MyST recognise ```{mermaid}``` fenced blocks as directives.
myst_enable_extensions = ["colon_fence"]

# Generate anchors for headings up to level 3 so cross-file links of the form
# [text](some_page.md#a-heading-slug) resolve. Without this MyST only knows
# about explicit (target)= labels and silently emits xref warnings.
myst_heading_anchors = 3

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
nbsphinx_execute = "never"
html_logo = "_static/crocodile.png"
html_favicon = "_static/crocodile.png"

# Banner on every page asking users to tell us how they use CrocoDash.
# Readers can close it; announcement.js remembers that per form URL.
USE_CASE_FORM_URL = "https://forms.gle/UsgxpqCTyHGn4sLJ9"
html_theme_options = {
    "announcement": (
        "<strong>Using CrocoDash?</strong> Tell us about your project in a "
        f'<a href="{USE_CASE_FORM_URL}" target="_blank" rel="noopener">2-minute form</a>.'
    ),
}
html_css_files = ["announcement.css"]
html_js_files = [("announcement.js", {"data-key": USE_CASE_FORM_URL})]
