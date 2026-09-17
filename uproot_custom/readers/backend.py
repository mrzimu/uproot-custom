from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Literal

_BACKEND_OPTIONS = frozenset({"cpp", "python", "forth"})
_BACKEND_TYPE = Literal["cpp", "python", "forth"]

_backend: _BACKEND_TYPE | None = None


def get() -> _BACKEND_TYPE:
    """
    Return the current reader backend.

    The backend is resolved in the following order of priority:
    explicitly set value via :func:`set` >
    `UPROOT_CUSTOM_READER_BACKEND` environment variable >
    default `"cpp"`.

    Returns:
        The current reader backend (`"cpp"`, `"python"`, or `"forth"`).

    Raises:
        ValueError: If the `UPROOT_CUSTOM_READER_BACKEND` environment
            variable is set to an unrecognized value.
    """
    global _backend
    if _backend is not None:
        return _backend

    env = os.environ.get("UPROOT_CUSTOM_READER_BACKEND", "cpp")
    if env not in _BACKEND_OPTIONS:
        raise ValueError(
            f"Unknown reader backend: {env!r} (from $UPROOT_CUSTOM_READER_BACKEND). "
            f"Valid backends: {sorted(_BACKEND_OPTIONS)}."
        )
    _backend = env
    return _backend


def set(backend: _BACKEND_TYPE) -> None:
    """
    Set the current reader backend.

    This overrides the `UPROOT_CUSTOM_READER_BACKEND` environment
    variable and the default `"cpp"`.

    Args:
        backend: The reader backend to use. Must be one of `"cpp"`,
            `"python"`, or `"forth"`.

    Raises:
        ValueError: If *backend* is not a recognized reader backend.
    """
    if backend not in _BACKEND_OPTIONS:
        raise ValueError(
            f"Unknown reader backend: {backend!r}. "
            f"Valid backends: {sorted(_BACKEND_OPTIONS)}."
        )

    global _backend
    _backend = backend


@contextmanager
def use(backend: _BACKEND_TYPE):
    """
    Context manager to temporarily switch the reader backend.

    The original backend is restored when exiting the `with` block.

    Example::

        from uproot_custom.readers import backend

        with backend.use("python"):
            branch.array()

    Args:
        backend: The reader backend to use within the context.
            Must be one of `"cpp"`, `"python"`, or `"forth"`.

    Raises:
        ValueError: If *backend* is not a recognized reader backend.
    """
    old = get()
    set(backend)
    try:
        yield
    finally:
        set(old)
