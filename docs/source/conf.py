# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# -- Project information -----------------------------------------------------

project = "FrostPlanner"
author = "Sebastiano Gaiardelli"
copyright = f"2025, {author}"

try:
    release = _pkg_version("frost_planner")
except PackageNotFoundError:
    release = "0.0.0"
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "autoapi.extension",
    "myst_parser",
    "sphinx_copybutton",
]

exclude_patterns: list[str] = []
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Options for MyST --------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "smartquotes",
]
myst_heading_anchors = 3

# -- Options for sphinx-copybutton -------------------------------------------

# Strip the common interactive prompts so copied snippets are runnable as-is.
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

# -- Options for autodoc / napoleon ------------------------------------------

# Render type hints in the description rather than the signature so signatures
# stay readable when types get long (Pydantic models, generics, etc.).
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_attr_annotations = True
# Render the `Attributes:` section as an ``:ivar:`` field list instead of
# ``.. py:attribute::`` directives, so it does not clash with the attribute
# documentation autoapi already emits from class introspection.
napoleon_use_ivar = True

# -- Options for AutoAPI extension -------------------------------------------
# https://sphinx-autoapi.readthedocs.io/en/latest/reference/config.html

autoapi_type = "python"
autoapi_dirs = ["../../frost_planner"]
autoapi_root = "autoapi"
autoapi_keep_files = False
autoapi_add_toctree_entry = True
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_python_class_content = "both"
autoapi_member_order = "groupwise"

# -- Options for intersphinx -------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
}

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = f"{project} {release}"
