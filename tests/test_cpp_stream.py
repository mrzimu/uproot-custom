"""
The C++ backend's `BinaryStream`: counted regions, through a compiled reader.

The guard is C++-only, so the test drives `AnyClassReader` from Python: a
well-formed object passes, a wrong `fNBytes` is reported with both positions.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from uproot_custom.consts import kByteCountMask

cpp = pytest.importorskip("uproot_custom.cpp")


def _body(value: int) -> bytes:
    """
    A versioned object body: `fVersion` then one `int32` member.
    """
    return struct.pack(">h", 1) + struct.pack(">i", value)


def _payload(body: bytes, claimed: int | None = None) -> bytes:
    count = len(body) if claimed is None else claimed
    return struct.pack(">I", count | kByteCountMask) + body


def _read(payload: bytes, reader):
    data = np.frombuffer(payload, dtype=np.uint8)
    offsets = np.array([0, len(payload)], dtype=np.uint32)
    return cpp.read_data(data, offsets, 0, reader)


def test_a_counted_object_checks_its_byte_count():
    reader = cpp.AnyClassReader("c", [cpp.Int32Reader("v")])

    array = _read(_payload(_body(7)), reader)

    assert np.asarray(array[0]).tolist() == [7]


def test_a_wrong_byte_count_names_both_positions():
    reader = cpp.AnyClassReader("c", [cpp.Int32Reader("v")])

    with pytest.raises(RuntimeError, match=r"expected 14, got 10"):
        _read(_payload(_body(7), claimed=10), reader)


def test_a_pointer_object_checks_its_byte_count():
    reader = cpp.AnyPointerReader("p", cpp.Int32Reader("v"))
    body = struct.pack(">I", 0xFFFFFFFF) + b"TCls\x00" + struct.pack(">i", 7)
    payload = _payload(body)

    data, indexes = _read(payload, reader)

    assert np.asarray(data).tolist() == [7]
    assert np.asarray(indexes).tolist() == [0]
