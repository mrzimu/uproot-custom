from __future__ import annotations

from typing import Literal

import numpy as np

kNewClassTag = 0xFFFFFFFF
kByteCountMask = 0x40000000
kClassMask = 0x80000000
kIsReferenced = 1 << 4
kStreamedMemberwise = 1 << 14
kMapOffset = 2

#: An STL frame carries the value class's version only from this frame version
#: on, and only in member-wise form; `kSTLp`, a pointer to the same container,
#: uses 9 (`Collections.md` §6, §11.3).  Neither code survives in the file:
#: every `TStreamerSTL` element is written with `fType` 500 (`StreamerInfo.md`
#: §10), so the pointer is recognised from the type name ending in `*`.
STL_VERSION_WITH_VALUE_VERSION = 8
STL_VERSION_WITH_VALUE_VERSION_POINTER = 9


_MISSING = object()

TYPECODE = Literal["b", "B", "h", "H", "i", "I", "q", "Q", "f", "d"]
TYPECODE_TO_DTYPE = {
    "b": np.int8,
    "B": np.uint8,
    "h": np.int16,
    "H": np.uint16,
    "i": np.int32,
    "I": np.uint32,
    "q": np.int64,
    "Q": np.uint64,
    "f": np.float32,
    "d": np.float64,
}

#: numpy dtype name -> fixed-width ``struct`` typecode.  The platform-dependent
#: ``l``/``L`` are deliberately absent: ``array.array`` makes them 8 bytes on
#: Linux, and the machine has no coercer for them.
DTYPE_TO_TYPECODE = {
    "bool": "B",
    "uint8": "B",
    "uint16": "H",
    "uint32": "I",
    "uint64": "Q",
    "int8": "b",
    "int16": "h",
    "int32": "i",
    "int64": "q",
    "float32": "f",
    "float64": "d",
}
