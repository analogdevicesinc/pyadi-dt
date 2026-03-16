# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# http://www.sphinx-doc.org/en/master/config

# -- Path setup --------------------------------------------------------------

import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2].resolve()))

import adidt  # isort:skip

# -- Project information -----------------------------------------------------

project = "pyadi-dt"
year_now = datetime.datetime.now().year
copyright = f"2024-{year_now}, Analog Devices, Inc."
author = "Analog Devices, Inc."

# The full version, including alpha/beta/rc tags
release = adidt.__version__
version = release

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.coverage",
    "sphinx.ext.githubpages",
    "myst_parser",
    "sphinx_click",
    "sphinxcontrib.mermaid",
    "adi_doctools",
]

needs_extensions = {"adi_doctools": "0.4.39"}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = []

# Configuration of sphinx.ext.coverage
coverage_show_missing_items = True

# Link check configuration
linkcheck_ignore = [
    r"https://ez.analog.com.*",
]

# -- MyST-Parser configuration -----------------------------------------------

myst_enable_extensions = [
    "colon_fence",  # ::: fences for directives
    "deflist",  # Definition lists
    "html_image",  # HTML image tags
    "linkify",  # Auto-detect URLs
    "replacements",  # Text replacements
    "smartquotes",  # Smart quotes
    "tasklist",  # GitHub-style task lists
]

# -- Autodoc configuration ---------------------------------------------------

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
}

# Napoleon settings for docstring parsing
napoleon_google_style = True
napoleon_numpy_style = True
napoleon_include_init_with_doc = True

# -- Options for HTML output -------------------------------------------------

html_theme = "cosmic"  # ADI theme (alias for "harmonic")
html_favicon = "_static/media/pyadi-dt_72.png"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

html_theme_options = {
    "light_logo": os.path.join("media", "pyadi-dt.svg"),
    "dark_logo": os.path.join("media", "pyadi-dt_w.svg"),
}

# -- Options for source files ------------------------------------------------

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Root document
root_doc = "index"
