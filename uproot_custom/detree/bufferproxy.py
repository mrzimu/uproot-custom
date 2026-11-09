from __future__ import annotations

import array

import numpy as np

from uproot_custom.consts import TYPECODE, TYPECODE_TO_DTYPE


class _OwnedArrayView(np.ndarray):
    """
    Keep the detree C owner alive through NumPy's base-class views.

    detree's compiled backends return an `_OwnedArray` whose `_owner`
    attribute releases the C buffer.  `np.asarray` strips the subclass and
    only keeps the memoryview/ctypes base, which does not carry the Python
    owner attribute; this tiny subclass propagates the owner through
    `__array_finalize__` so the final ndarray's base chain retains it.
    """

    def __array_finalize__(self, obj):
        self._owner = getattr(obj, "_owner", None)


class BufferProxy:
    __slots__ = ("_storage", "init", "kind", "typecode")

    def __init__(self, typecode: TYPECODE, init=(), *, kind: str = "data"):
        self.typecode = typecode
        self.init = tuple(init)
        self.kind = kind
        self._allocate()

    def _allocate(self):
        self._storage = array.array(self.typecode, self.init)

    @property
    def dtype(self):
        return TYPECODE_TO_DTYPE[self.typecode]

    def reset(self):
        """
        Empty the buffer, and let go of the storage a previous run filled.
        """
        self._allocate()

    def append(self, value):
        self._storage.append(value)

    def extend(self, values):
        self._storage.extend(values)

    def __len__(self):
        return len(self._storage)

    def __getitem__(self, index):
        return self._storage[index]

    def __setitem__(self, index, value):
        self._storage[index] = value

    def __array__(self, dtype=None, copy=None):
        # A compiled backend hands back a NumPy subclass whose ``_owner`` keeps
        # the C buffer alive.  ``np.asarray`` on that subclass would return a
        # base-class view and drop the owner, so return the adopted array itself
        # when no conversion is requested.
        if isinstance(self._storage, np.ndarray):
            if dtype is None and not copy:
                return self._storage
            return np.asarray(self._storage, dtype=dtype)
        return np.asarray(self._storage, dtype=dtype)

    def adopt(self, values: np.ndarray):
        """
        Take the array the machine filled, without copying it.
        """
        if values.dtype != self.dtype:
            raise TypeError(f"cannot adopt a {values.dtype} array into a {self.dtype} buffer")
        if getattr(values, "_owner", None) is not None:
            values = values.view(_OwnedArrayView)
        self._storage = values
