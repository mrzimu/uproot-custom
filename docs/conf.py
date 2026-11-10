# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import sys
from pathlib import Path

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Uproot-custom"
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
    "sphinxext.rediraffe",
]

# Keep the URLs that earlier releases published working after the documentation
# was restructured. Keys and values are paths relative to this directory.
rediraffe_redirects = {
    "get-started.md": "getting-started.md",
    "tutorial/customize-factory-reader.md": "tutorial/index.md",
    "tutorial/customize-factory-reader/pipeline.md": "concepts/how-it-works.md",
    "tutorial/customize-factory-reader/investigate-data.md": "tutorial/investigate-data.md",
    "tutorial/customize-factory-reader/reader-and-factory.md": "tutorial/write-a-reader.md",
    "tutorial/customize-factory-reader/project-setup.md": "tutorial/package-your-project.md",
    "tutorial/customize-factory-reader/port-to-cpp.md": "advanced/cpp-reader.md",
    "reference/reader-backends.md": "concepts/choosing-a-route.md",
    "reference/detree-stack.md": "reference/detree-dsl.md",
}

templates_path = ["_templates"]
exclude_patterns = []

# Section labels are qualified with the document name, so "How it works" in two
# pages does not collide.
autosectionlabel_prefix_document = True

# The API reference inherits docstrings from uproot, which use :doc:/:ref: roles
# that only resolve inside uproot's own documentation. Nothing in this project's
# pages uses those roles, so the warnings are noise; MyST links are still checked.
suppress_warnings = ["ref.doc", "ref.ref"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Furo has no navigation-depth options: the sidebar shows the whole toctree and
# the right-hand column shows the local table of contents at every level. The
# only page that needed a shallower TOC sets `tocdepth` in its own front matter.
html_theme = "furo"
html_static_path = ["_static"]

html_theme_options = {
    "source_repository": "https://github.com/mrzimu/uproot-custom/",
    "source_branch": "main",
    "source_directory": "docs/",
    "top_of_page_button": "edit",
}

html_title = "Uproot-custom"

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

# Generate an id for every heading up to level 3, so cross-page links such as
# `how-it-works.md#stage-2-build-readers` resolve.
myst_heading_anchors = 3

# -- Options for internationalization --------------------------------------------
locale_dirs = ["locales/"]
gettext_compact = False  # Do not compact message files
language = "en"  # Default language

# -- Options for autodoc ---------------------------------------------------------
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
            sys.executable,
            "-m",
            "sphinx.ext.apidoc",
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
    "auto": ("../kernel", ["include/uproot-custom/uproot-custom.hh", "src/uproot-custom.cc"]),
}

sys.path.insert(0, str(Path(__file__).parent.parent.resolve() / "doxygen" / "xml"))


def run_doxygen():
    """Run the doxygen make command in the designated folder."""
    import subprocess

    doxygen_file = Path(__file__).parent / "Doxyfile"
    working_dir = doxygen_file.parent
    result = subprocess.run(
        ["doxygen", str(doxygen_file)],
        cwd=working_dir,
        capture_output=True,
        text=True,
        check=False,
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
