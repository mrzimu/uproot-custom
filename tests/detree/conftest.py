"""
Skip the detree-vm tests when the optional dependency is not installed.

The execution API lives in `uproot_custom.detree.run`, whose compiler imports
`detree`; without the package there is nothing to exercise here.
"""

from importlib.util import find_spec

if find_spec("detree") is None:
    collect_ignore_glob = ["test_*.py"]
