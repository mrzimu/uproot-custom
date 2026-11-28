"""
A pointer to an STL container is written as the container itself.

`std::vector<int> *m` has `fSTLtype` 41 and a type name ending in `*`, which is
what makes ROOT read it as `kSTLp` (`Collections.md` §11.3).  Its bytes carry no
pointer tag and no null marker -- a null pointer is a count of 0 -- so it is
read by the STL factories, never by `AnyPointerFactory`, and its frame carries
the value class's version only from frame version 9
(`TStreamerInfoReadBuffer.cxx`, the `kSTLp` case).

The hand-built cases decode through the factory the routing picks, so a wrong
route fails the test even when both readers agree.  `test_stl_pointer.root`
holds the same family as ROOT writes it, including a null pointer, entries
whose count changes, and a fixed array of pointers, whose collections share one
frame (`Collections.md` §11.1).
"""

from __future__ import annotations

import struct

import awkward as ak
import numpy as np
import pytest

from uproot_custom import python
from uproot_custom.consts import (
    STL_VERSION_WITH_VALUE_VERSION,
    STL_VERSION_WITH_VALUE_VERSION_POINTER,
    kByteCountMask,
    kStreamedMemberwise,
)
from uproot_custom.detree import interp
from uproot_custom.detree.run import read_data
from uproot_custom.factories import (
    AnyPointerFactory,
    STLMapFactory,
    STLSeqFactory,
    STLStringFactory,
    build_factory,
)


def _u32(value):
    return struct.pack(">I", value)


def _i16(value):
    return struct.pack(">h", value)


def _decode(info, payload, all_streamer_info=None):
    """
    Build the reader the routing picks, then decode *payload* three ways.
    """
    factory = build_factory(info, all_streamer_info or {}, "")
    py_reader = factory.build_python_reader()
    native_reader = factory.build_detree_reader()

    data = np.frombuffer(payload, dtype=np.uint8)
    offsets = np.asarray([0, len(payload)], dtype=np.int64)
    expected = python.read_data(data, offsets, 0, py_reader)
    for actual in (
        interp.read_data(native_reader, payload, offsets, 0),
        read_data(native_reader, payload, offsets, 0),
    ):
        assert len(actual) == len(expected)
        for left, right in zip(expected, actual):
            np.testing.assert_array_equal(np.asarray(left), np.asarray(right))

    return expected


@pytest.mark.parametrize(
    ("cur_streamer_info", "factory_type", "value_version_min"),
    [
        (
            {"fTypeName": "vector<int>*", "fType": 500, "fSTLtype": 41},
            STLSeqFactory,
            STL_VERSION_WITH_VALUE_VERSION_POINTER,
        ),
        (
            {"fTypeName": "map<int,double>*", "fType": 500, "fSTLtype": 44},
            STLMapFactory,
            STL_VERSION_WITH_VALUE_VERSION_POINTER,
        ),
        (
            {"fTypeName": "string*", "fType": 500, "fSTLtype": 365},
            STLStringFactory,
            None,
        ),
        (
            {"fTypeName": "vector<int>", "fType": 500, "fSTLtype": 1},
            STLSeqFactory,
            STL_VERSION_WITH_VALUE_VERSION,
        ),
    ],
)
def test_a_pointer_to_a_collection_goes_to_its_stl_factory(
    cur_streamer_info, factory_type, value_version_min
):
    """
    The pointer spelling must not send it to `AnyPointerFactory`.

    `AnyPointerFactory` reads ROOT's `read_object_any` protocol, which a
    pointer to a collection does not use (`Collections.md` §11.3).
    """
    cur_streamer_info["fName"] = "m"

    factory = build_factory(cur_streamer_info, {}, "")

    assert isinstance(factory, factory_type)
    assert getattr(factory, "value_version_min", None) == value_version_min


def test_a_pointer_to_a_class_is_still_an_object_pointer():
    """
    The routing change is limited to elements of the `TStreamerSTL` family.

    Those are the only ones that carry `fSTLtype`; a class pointer has none.
    """
    cur_streamer_info = {"fName": "m", "fTypeName": "MyClass*", "fType": 64}
    all_streamer_info = {"MyClass": [{"fName": "x", "fTypeName": "int", "fType": 3}]}

    factory = build_factory(cur_streamer_info, all_streamer_info, "")

    assert isinstance(factory, AnyPointerFactory)


#: A value class with two members, so a member-wise frame has two columns.
VALUE_CLASS = {
    "MyClass": [
        {"fName": "a", "fTypeName": "int", "fType": 3},
        {"fName": "b", "fTypeName": "double", "fType": 8},
    ]
}


def test_a_memberwise_pointer_to_a_vector_reads_the_value_version_from_9():
    info = {"fName": "m", "fTypeName": "vector<MyClass>*", "fType": 500, "fSTLtype": 41}
    body = _u32(2) + struct.pack(">ii", 5, 6) + struct.pack(">dd", 1.5, 2.5)

    # Version 9 carries the value class's version, so its word is there too.
    with_version = (
        _u32((len(body) + 4) | kByteCountMask) + _i16(kStreamedMemberwise | 9) + _i16(1) + body
    )
    offsets, elements = _decode(info, with_version, VALUE_CLASS)
    np.testing.assert_array_equal(offsets, [0, 2])
    np.testing.assert_array_equal(elements[0], [5, 6])
    np.testing.assert_array_equal(elements[1], [1.5, 2.5])

    # Version 8 is below the pointer's boundary, so there is no version word.
    without_version = (
        _u32((len(body) + 2) | kByteCountMask) + _i16(kStreamedMemberwise | 8) + body
    )
    offsets, elements = _decode(info, without_version, VALUE_CLASS)
    np.testing.assert_array_equal(offsets, [0, 2])
    np.testing.assert_array_equal(elements[0], [5, 6])
    np.testing.assert_array_equal(elements[1], [1.5, 2.5])


def test_a_null_pointer_is_a_count_of_zero():
    """
    There is no null marker to consume (`Collections.md` §11.3).

    A reader that looked for one would be misaligned for the rest of the entry.
    """
    info = {"fName": "m", "fTypeName": "vector<int>*", "fType": 500, "fSTLtype": 41}
    body = _u32(0)
    payload = _u32((len(body) + 2) | kByteCountMask) + _i16(1) + body

    offsets, values = _decode(info, payload)
    np.testing.assert_array_equal(offsets, [0, 0])
    assert values.size == 0


# -- the ROOT-written fixture --------------------------------------------------


def _array(test_contexts, branch):
    test_file = test_contexts["stl_pointer"]["file"]
    return test_file["tree"][branch].array(library="ak")


def _expected(i):
    """
    The values `TSTLPointer::fill(i)` writes, one entry each.

    Entry 0 leaves every pointer null, and the count is `1 + i % 3`, so an
    entry that reused the previous entry's count would show up here.  The
    array's two collections hold `1 + i % 2` and `i % 3` values, so taking one
    count for the whole run would show up too.
    """
    if i == 0:
        return {
            "m_pmap": [],
            "m_pstr": "",
            "m_pvec": [],
            "m_pvecarr[2]": [[], []],
            "m_pvecnamed": [],
        }

    count = 1 + i % 3
    return {
        "m_pmap": [{"key": f"k{k}", "val": [f"v{100 * i + k}"]} for k in range(count)],
        "m_pstr": f"s{i}",
        "m_pvec": [100 * i + k for k in range(count)],
        "m_pvecarr[2]": [
            [1000 * i + k for k in range(1 + i % 2)],
            [2000 * i + k for k in range(i % 3)],
        ],
        "m_pvecnamed": [{"fName": f"n{i}_{k}", "fTitle": ""} for k in range(count)],
    }


@pytest.mark.parametrize("entry", [0, 1, 3, 9])
@pytest.mark.parametrize("branch", sorted(_expected(1)))
def test_the_values_are_the_ones_that_went_in(test_contexts, branch, entry):
    assert ak.to_list(_array(test_contexts, branch)[entry]) == _expected(entry)[branch]


@pytest.mark.parametrize("branch", ["m_pvec", "m_pvecnamed", "m_pmap"])
def test_the_run_has_one_element_per_entry(test_contexts, branch):
    """
    The count is each entry's own, not the previous entry's.
    """
    rows = ak.to_list(_array(test_contexts, branch))
    assert [len(row) for row in rows] == [0] + [1 + i % 3 for i in range(1, 10)]
