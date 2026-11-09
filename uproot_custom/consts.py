from __future__ import annotations

from typing import Literal

import numpy as np

kNewClassTag = 0xFFFFFFFF
kByteCountMask = 0x40000000
kClassMask = 0x80000000
kIsReferenced = 1 << 4
kStreamedMemberwise = 1 << 14
kMapOffset = 2


_MISSING = object()

TYPECODE = Literal["b", "B", "h", "H", "i", "I", "l", "L", "q", "Q", "f", "d"]
TYPECODE_TO_DTYPE = {
    "b": np.int8,
    "B": np.uint8,
    "h": np.int16,
    "H": np.uint16,
    "i": np.int32,
    "I": np.uint32,
    "l": np.int32,
    "L": np.uint32,
    "q": np.int64,
    "Q": np.uint64,
    "f": np.float32,
    "d": np.float64,
}

#: numpy dtype name -> fixed-width ``struct`` typecode.  Only the codes whose
#: ``array.array`` width matches the dtype: ``l``/``L`` are 8 bytes on Linux but
#: map to a 32-bit numpy dtype here, and the machine has no coercer for them.
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
