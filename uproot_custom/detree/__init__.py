"""
Detree: the reader DSL, its compiler, and the detree-vm execution seam.

* `uproot_custom.detree.decl` + `uproot_custom.detree.builtin` -- the
  declarative readers the frontend compiles, and the built-in implementations
  of the ROOT types;
* `uproot_custom.detree.compiler` -- `compile_reader` builds detree-vm IR
  and hands it to `detree.compile` for optimization and lowering;
* `uproot_custom.detree.run` -- caches a `Compiled` per reader structure,
  runs one basket on detree-vm, and writes the machine's buffers back into the
  reader.

`uproot_custom.detree.interp` is the Python executor of the same reader
methods, used for debugging and as an oracle in the differential tests.
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

#: Environment variable a fresh `get_impl` reads.
IMPL_ENV = "UPROOT_CUSTOM_DETREE_BACKEND"

_IMPL_OPTIONS = frozenset({"rust", "python", "cpp"})
_IMPL_TYPE = Literal["rust", "python", "cpp"]

_backend: _IMPL_TYPE | None = None


def get_impl() -> _IMPL_TYPE:
    """
    Get the current backend for detree.

    Returns:
        _IMPL_TYPE: The currently set backend.
    """
    global _backend
    if _backend is None:
        _backend = os.getenv(IMPL_ENV, "rust")
        if _backend not in _IMPL_OPTIONS:
            raise ValueError(f"Invalid backend: {_backend}")
    return _backend


def set_impl(backend: _IMPL_TYPE) -> None:
    """
    Set the backend for detree.

    Args:
        backend (_IMPL_TYPE): The backend to set.
    """
    if backend not in _IMPL_OPTIONS:
        raise ValueError(f"Invalid backend: {backend}")
    global _backend
    _backend = backend


@contextmanager
def use_impl(backend: _IMPL_TYPE):
    """
    Context manager to temporarily set the backend for detree.

    Args:
        backend (_IMPL_TYPE): The backend to use within the context.
    """
    old = get_impl()
    set_impl(backend)
    try:
        yield
    finally:
        set_impl(old)


__all__ = [
    "IMPL_ENV",
    "Buffer",
    "BufferProxy",
    "Child",
    "ChildList",
    "Const",
    "Reader",
    "State",
    "Stream",
    "get_impl",
    "reader",
    "set_impl",
    "use_impl",
]
