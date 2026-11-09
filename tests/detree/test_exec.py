"""
The three executors agree: the Python readers, the Python interpreter, and the
native detree-vm machine.

Every case builds a basket by hand, decodes it with

* `uproot_custom.python` -- the independent implementation, the oracle;
* `uproot_custom.detree.interp` -- the reader's own methods, run in Python;
* `uproot_custom.detree.read_data` -- the reader compiled to detree-vm and run,

and asserts the raw results are equal element for element.  A disagreement
therefore names the layer that is wrong: the reader contract, the compiler, or
the machine.
"""

from __future__ import annotations

import struct

import numpy as np

import uproot_custom.detree.builtin as native
from uproot_custom import python
from uproot_custom.consts import (
    kByteCountMask,
    kIsReferenced,
    kNewClassTag,
    kStreamedMemberwise,
)
from uproot_custom.detree import interp
from uproot_custom.detree.run import read_data


# -- helpers -------------------------------------------------------------------
def _u32(value):
    return struct.pack(">I", value)


def _i16(value):
    return struct.pack(">h", value)


def _header(body, version=1):
    """
    A ROOT container header: byte count (masked), then the version.
    """
    return _u32(len(body) | kByteCountMask) + _i16(version) + body


def _assert_raw(expected, actual):
    if expected is None:
        assert actual is None
    elif isinstance(expected, tuple):
        assert isinstance(actual, tuple) and len(expected) == len(actual)
        for left, right in zip(expected, actual):
            _assert_raw(left, right)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual)
        for left, right in zip(expected, actual):
            _assert_raw(left, right)
    else:
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(actual))


def _check(py_reader, native_reader, payload, offsets, cursor_offset=0):
    """
    Decode *payload* three ways; return the oracle's raw result.
    """
    data = np.frombuffer(payload, dtype=np.uint8)
    expected = python.read_data(
        data, np.asarray(offsets, dtype=np.int64), cursor_offset, py_reader
    )
    _assert_raw(expected, interp.read_data(native_reader, payload, offsets, cursor_offset))
    _assert_raw(expected, read_data(native_reader, payload, offsets, cursor_offset))
    return expected


# -- leaves --------------------------------------------------------------------
def test_primitive_int32():
    _check(
        python.PrimitiveReader("p", "int32"),
        native.PrimitiveReader("p", typecode="i"),
        struct.pack(">iii", 1, -2, 3),
        [0, 4, 8, 12],
    )


def test_a_fixed_width_basket_derives_its_offsets():
    payload = struct.pack(">ii", 1, 2)
    reader = native.PrimitiveReader("p", typecode="i")

    via_python = interp.read_data(reader, payload, None, nbyte=4)
    via_vm = read_data(reader, payload, None, nbyte=4)

    np.testing.assert_array_equal(via_python, [1, 2])
    np.testing.assert_array_equal(via_vm, [1, 2])


def test_primitive_float64():
    _check(
        python.PrimitiveReader("p", "float64"),
        native.PrimitiveReader("p", typecode="d"),
        struct.pack(">ddd", 1.5, -2.25, 3.75),
        [0, 8, 16, 24],
    )


def test_primitive_bool():
    _check(
        python.PrimitiveReader("p", "bool"),
        native.PrimitiveReader("p", typecode="B"),
        bytes([0, 1, 1]),
        [0, 1, 2, 3],
    )


def test_tstring():
    payload = struct.pack(">B", 3) + b"abc" + struct.pack(">B", 0)
    _check(
        python.TStringReader("s", False),
        native.TStringReader("s", with_header=False),
        payload,
        [0, 4, 5],
    )


def test_stlstring():
    body = struct.pack(">B", 3) + b"xyz"
    payload = _header(body)
    _check(
        python.STLStringReader("s", True),
        native.STLStringReader("s", with_header=True),
        payload,
        [0, len(payload)],
    )


def test_tarray():
    body = struct.pack(">I", 3) + struct.pack(">ddd", 1.0, 2.0, 3.0)
    _check(
        python.TArrayReader("a", "float64"),
        native.TArrayReader("a", typecode="d"),
        body,
        [0, len(body)],
    )


def test_tobject_without_reference_bits():
    payload = _i16(1) + struct.pack(">i", 42) + _u32(0)
    _check(
        python.TObjectReader("o", True),
        native.TObjectReader("o", keep_data=True),
        payload,
        [0, len(payload)],
    )


def test_tobject_with_reference_bits():
    payload = _i16(1) + struct.pack(">i", 42) + _u32(kIsReferenced) + struct.pack(">H", 7)
    _check(
        python.TObjectReader("o", True),
        native.TObjectReader("o", keep_data=True),
        payload,
        [0, len(payload)],
    )


def test_tobject_discards_its_data():
    payload = _i16(1) + struct.pack(">i", 42) + _u32(0)
    _check(
        python.TObjectReader("o", False),
        native.TObjectReader("o", keep_data=False),
        payload,
        [0, len(payload)],
    )


def test_empty_reader():
    _check(
        python.EmptyReader("e"),
        native.EmptyReader("e"),
        b"",
        [0, 0],
    )


# -- containers ----------------------------------------------------------------
def test_stl_sequence():
    body = struct.pack(">I", 3) + struct.pack(">ddd", 1.0, 2.0, 3.0)
    payload = _header(body)
    _check(
        python.STLSeqReader("v", True, python.PrimitiveReader("e", "float64")),
        native.STLSeqReader(
            "v", with_header=True, element=native.PrimitiveReader("e", typecode="d")
        ),
        payload,
        [0, len(payload)],
    )


def test_stl_sequence_of_strings():
    body = struct.pack(">I", 2) + struct.pack(">B", 3) + b"abc" + struct.pack(">B", 1) + b"z"
    payload = _header(body)
    _check(
        python.STLSeqReader("v", True, python.STLStringReader("e", False)),
        native.STLSeqReader(
            "v", with_header=True, element=native.STLStringReader("e", with_header=False)
        ),
        payload,
        [0, len(payload)],
    )


def test_stl_sequence_memberwise():
    """
    A memberwise container is read field by field across all elements.
    """
    element_version = _i16(0) + b"\x00\x00\x00\x00"
    body = struct.pack(">I", 2) + struct.pack(">ii", 5, 6) + struct.pack(">dd", 1.5, 2.5)
    payload = (
        _u32(len(body) | kByteCountMask)
        + _i16(kStreamedMemberwise | 1)
        + element_version
        + body
    )
    _check(
        python.STLSeqReader(
            "v",
            True,
            python.GroupReader(
                "e",
                [python.PrimitiveReader("a", "int32"), python.PrimitiveReader("b", "float64")],
            ),
        ),
        native.STLSeqReader(
            "v",
            with_header=True,
            element=native.GroupReader(
                "e",
                elements=[
                    native.PrimitiveReader("a", typecode="i"),
                    native.PrimitiveReader("b", typecode="d"),
                ],
            ),
        ),
        payload,
        [0, len(payload)],
    )


def test_stl_map():
    body = struct.pack(">I", 2) + struct.pack(">idid", 1, 1.5, 2, 2.5)
    payload = (
        _u32(len(body) | kByteCountMask)
        + _i16(1)  # container version
        + _i16(1)  # element version
        + body
    )
    _check(
        python.STLMapReader(
            "m",
            True,
            python.PrimitiveReader("k", "int32"),
            python.PrimitiveReader("v", "float64"),
        ),
        native.STLMapReader(
            "m",
            with_header=True,
            key=native.PrimitiveReader("k", typecode="i"),
            value=native.PrimitiveReader("v", typecode="d"),
        ),
        payload,
        [0, len(payload)],
    )


def test_cstyle_array_fixed():
    payload = struct.pack(">iii", 7, 8, 9)
    _check(
        python.CStyleArrayReader("a", 3, python.PrimitiveReader("e", "int32")),
        native.CStyleArrayReader(
            "a", flat_size=3, element=native.PrimitiveReader("e", typecode="i")
        ),
        payload,
        [0, len(payload)],
    )


def test_cstyle_array_jagged():
    payload = bytes([1, 2, 3, 4, 5])
    _check(
        python.CStyleArrayReader("a", -1, python.PrimitiveReader("e", "uint8")),
        native.CStyleArrayReader(
            "a", flat_size=-1, element=native.PrimitiveReader("e", typecode="B")
        ),
        payload,
        [0, 3, 5],
    )


def test_group():
    payload = struct.pack(">id", 7, 1.5)
    _check(
        python.GroupReader(
            "g", [python.PrimitiveReader("i", "int32"), python.PrimitiveReader("d", "float64")]
        ),
        native.GroupReader(
            "g",
            elements=[
                native.PrimitiveReader("i", typecode="i"),
                native.PrimitiveReader("d", typecode="d"),
            ],
        ),
        payload,
        [0, len(payload)],
    )


def test_any_class():
    body = _i16(1) + struct.pack(">i", 3)
    payload = _u32(len(body) | kByteCountMask) + body
    _check(
        python.AnyClassReader("c", [python.PrimitiveReader("a", "int32")]),
        native.AnyClassReader("c", elements=[native.PrimitiveReader("a", typecode="i")]),
        payload,
        [0, len(payload)],
    )


# -- pointers ------------------------------------------------------------------
def test_any_pointer_null():
    payload = _u32(0)
    _check(
        python.AnyPointerReader("p", python.EmptyReader("e")),
        native.AnyPointerReader("p", element=native.EmptyReader("e")),
        payload,
        [0, 4],
    )


def test_any_pointer_new_class_with_an_empty_payload():
    name = b"TCls\x00"
    body = _u32(kNewClassTag) + name
    payload = _u32(len(body) | kByteCountMask) + body
    _check(
        python.AnyPointerReader("p", python.EmptyReader("e")),
        native.AnyPointerReader("p", element=native.EmptyReader("e")),
        payload,
        [0, len(payload)],
    )


def test_any_pointer_new_class_with_a_value():
    name = b"TCls\x00"
    body = _u32(kNewClassTag) + name + struct.pack(">i", 99)
    payload = _u32(len(body) | kByteCountMask) + body
    _check(
        python.AnyPointerReader("p", python.PrimitiveReader("e", "int32")),
        native.AnyPointerReader("p", element=native.PrimitiveReader("e", typecode="i")),
        payload,
        [0, len(payload)],
    )


def test_any_pointer_back_reference():
    name = b"TCls\x00"
    first_body = _u32(kNewClassTag) + name
    first = _u32(len(first_body) | kByteCountMask) + first_body
    # the object reference is keyed by ``start_pos + kMapOffset``: 0 + 2 here
    second = _u32(4 | kByteCountMask) + _u32(2)
    payload = first + second
    offsets = [0, len(first), len(payload)]
    _check(
        python.AnyPointerReader("p", python.EmptyReader("e")),
        native.AnyPointerReader("p", element=native.EmptyReader("e")),
        payload,
        offsets,
    )
