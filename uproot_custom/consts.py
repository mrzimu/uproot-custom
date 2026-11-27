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
#: on, and only in member-wise form; `kSTLp` uses 9 (`Collections.md` §6).
STL_VERSION_WITH_VALUE_VERSION = 8
STL_VERSION_WITH_VALUE_VERSION_POINTER = 9

#: Streamer-element kinds of a collection: `kSTL` is an inline container and
#: `kSTLp` a pointer to one.  Both put the same bytes on disk, except for the
#: frame version at which the value class's version follows
#: (`TStreamerInfoReadBuffer.cxx`, the `kSTL` and `kSTLp` cases).
kSTL = 500
kSTLp = 501


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
