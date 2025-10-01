# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "uproot-custom"
copyright = "2025, Mingrun Li"
author = "Mingrun Li"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx_design",
    "sphinx.ext.ifconfig",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.intersphinx",
    "sphinx.ext.graphviz",
    "sphinx_togglebutton",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_togglebutton",
]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]

html_theme_options = {
    "show_navbar_depth": 2,
    "navigation_depth": 2,
    "show_toc_level": 2,
    "home_page_in_toc": True,
}

html_title = "uproot-custom"

# -- Options for mermaid extension -----------------------------------------------
# https://sphinxcontrib-mermaid-demo.readthedocs.io/en/latest/index.html
mermaid_version = "11.6.0"
mermaid_params = ["-f"]

# -- Options for myst parser extension -----------------------------------------------
# https://myst-parser.readthedocs.io/en/latest/sphinx.html
myst_enable_extensions = [
    "attrs_block",
    "attrs_inline",
    "colon_fence",
]

# -- Options for internationalization -----------------------------------------------
locale_dirs = ["locales/"]
gettext_compact = False  # Do not compact message files
language = "en"  # Default language
