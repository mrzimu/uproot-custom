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
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "breathe",
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

# -- Options for myst parser extension -------------------------------------------
# https://myst-parser.readthedocs.io/en/latest/sphinx.html
myst_enable_extensions = [
    "attrs_block",
    "attrs_inline",
    "colon_fence",
]

# -- Options for internationalization --------------------------------------------
locale_dirs = ["locales/"]
gettext_compact = False  # Do not compact message files
language = "en"  # Default language

# -- Options for autodoc ---------------------------------------------------------
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

apidoc_modules = [
    {
        "path": "../uproot_custom",
        "destination": "./reference/api",
        "automodule_options": {
            "members": True,
            "undoc-members": True,
            "show-inheritance": True,
            "show-source": True,
        },
    }
]


def run_sphinx_apidoc():
    """Run sphinx-apidoc to auto-generate reStructuredText files for modules."""
    import subprocess

    for module in apidoc_modules:
        cmd = [
            "sphinx-apidoc",
            "-o",
            str(Path(__file__).parent / module["destination"]),
            str(Path(__file__).parent / module["path"]),
            "--force",
            "-d",
            "10",
            "-T",
        ]
        subprocess.run(cmd, check=True)


# -- Options for breathe ---------------------------------------------------------
breathe_projects = {
    "uproot_custom_cpp": "../build/doxygen/xml",
}
breathe_default_project = "uproot_custom_cpp"
breathe_projects_source = {
    "auto": ("../cpp", ["include/uproot-custom/uproot-custom.hh", "src/uproot-custom.cc"]),
}

sys.path.insert(0, str(Path(__file__).parent.parent.resolve() / "doxygen" / "xml"))


def run_doxygen():
    """Run the doxygen make command in the designated folder."""
    import subprocess
    import os

    doxygen_file = Path(__file__).parent / "Doxyfile"
    working_dir = doxygen_file.parent
    result = subprocess.run(
        ["doxygen", str(doxygen_file)],
        cwd=working_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Doxygen failed with the following output:")
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Doxygen execution failed")


def run_doxygen_and_apidoc():
    run_doxygen()
    run_sphinx_apidoc()


def setup(app):
    app.connect("builder-inited", lambda app: run_doxygen_and_apidoc())


run_doxygen_and_apidoc()
