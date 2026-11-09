"""
Detree: the reader DSL, its compiler, and the detree-vm execution seam.

* `uproot_custom.detree.decl` + `uproot_custom.detree.builtin` -- the
  declarative readers the frontend compiles, and the built-in implementations
  of the ROOT types;
* `uproot_custom.detree.compiler.frontend` -- `compile_reader` builds detree-vm
  IR and hands it to `detree.compile` for optimization and lowering;
* `uproot_custom.detree.run` -- caches the compiled module bytes per reader
  structure, builds a machine for one basket, and writes its buffers back into
  the reader.

`uproot_custom.detree.interp` is the Python executor of the same reader
methods, used for debugging and as an oracle in the differential tests.

`get_impl`, `set_impl` and `use_impl` exist for internal tests only and are
not part of the public API; Detree-VM's official release ships the Rust
machine only.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Literal

from uproot_custom.detree.bufferproxy import BufferProxy
from uproot_custom.detree.decl import (
    Buffer,
    Child,
    ChildList,
    Const,
    Reader,
    State,
    reader,
)
from uproot_custom.detree.stream import Stream

#: Environment variable a fresh `get_impl` reads; internal testing only.
IMPL_ENV = "UPROOT_CUSTOM_DETREE_BACKEND"

_IMPL_OPTIONS = frozenset({"rust", "python", "cpp"})
_IMPL_TYPE = Literal["rust", "python", "cpp"]

_backend: _IMPL_TYPE | None = None


def get_impl() -> _IMPL_TYPE:
    """
    Get the Detree-VM machine used by the internal tests.

    Internal testing helper; not part of the public API. Detree-VM's official
    release ships the Rust machine only.

    Returns:
        _IMPL_TYPE: The currently selected machine.
    """
    global _backend
    if _backend is None:
        _backend = os.getenv(IMPL_ENV, "rust")
        if _backend not in _IMPL_OPTIONS:
            raise ValueError(f"Invalid backend: {_backend}")
    return _backend


def set_impl(backend: _IMPL_TYPE) -> None:
    """
    Select the Detree-VM machine used by the internal tests.

    Internal testing helper; not part of the public API.

    Args:
        backend (_IMPL_TYPE): The machine to select.
    """
    if backend not in _IMPL_OPTIONS:
        raise ValueError(f"Invalid backend: {backend}")
    global _backend
    _backend = backend


@contextmanager
def use_impl(backend: _IMPL_TYPE):
    """
    Temporarily select the Detree-VM machine used by the internal tests.

    Internal testing helper; not part of the public API.

    Args:
        backend (_IMPL_TYPE): The machine to use within the context.
    """
    old = get_impl()
    set_impl(backend)
    try:
        yield
    finally:
        set_impl(old)


__all__ = [
    "Buffer",
    "BufferProxy",
    "Child",
    "ChildList",
    "Const",
    "Reader",
    "State",
    "Stream",
    "reader",
]
