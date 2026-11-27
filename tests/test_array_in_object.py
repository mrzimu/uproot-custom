"""
A class with fixed array members, stored inside a collection.

ROOT writes such a member as a column, and the header of an array form covers
*every* object of the entry, not one object: one `fNBytes + fVersion` per
column per entry (`Collections.md` §11.1). The fixture holds a different number
of objects per entry, so a reader that took one header per object would
desynchronise on the second entry and fail loudly rather than return wrong
values.

The expectations are what `TArrayInObject::fill` writes, and they were confirmed
by reading this same file with ROOT itself (`TArrayInObjectHolder` through
`SetBranchAddress`). ROOT is the only oracle available here: `uproot` cannot
read the shared header of the `TString` and `vector` forms, nor the object-wise
map, so it is not a reference for them.
"""

from __future__ import annotations

import struct

import awkward as ak
import pytest

from uproot_custom.consts import kByteCountMask

COLUMNS = [
    "m_objs/m_objs.m_int[2]",
    "m_objs/m_objs.m_tstr[2]",
    "m_objs/m_objs.m_vec[2]",
    "m_objs/m_objs.m_mapvec[2]",
    "m_objs/m_objs.m_tnamed[2]",
]


def _branch(test_contexts, column):
    test_file = test_contexts["array_in_object"]["file"]
    test_file.file._array_cache = None
    return test_file["tree"][column]


def _objects_in(entry):
    """
    How many objects entry *entry* holds; `gen_ArrayInObject` writes `1 + i % 3`.
    """
    return 1 + entry % 3


def _expected(entry):
    """
    The values `TArrayInObject::fill(entry, j)` writes, for every object of the
    entry, as the column reads them.
    """
    objects = []
    for j in range(_objects_in(entry)):
        objects.append(
            {
                "m_objs/m_objs.m_int[2]": [100 * entry + 10 * j + k for k in (0, 1)],
                "m_objs/m_objs.m_tstr[2]": [f"t{entry}_{j}_{k}" for k in (0, 1)],
                "m_objs/m_objs.m_vec[2]": [[100 * entry + 10 * j + k] for k in (0, 1)],
                "m_objs/m_objs.m_mapvec[2]": [
                    [{"key": k, "val": [100 * entry + 10 * j + k]}] for k in (0, 1)
                ],
                "m_objs/m_objs.m_tnamed[2]": [
                    {"fName": f"n{entry}_{j}_{k}", "fTitle": ""} for k in (0, 1)
                ],
            }
        )
    return objects


@pytest.mark.parametrize("column", COLUMNS)
@pytest.mark.parametrize("entry", [0, 1, 2])
def test_the_values_are_the_ones_root_reads(test_contexts, column, entry):
    array = _branch(test_contexts, column).array(library="ak")
    expected = [obj[column] for obj in _expected(entry)]
    assert ak.to_list(array[entry]) == expected


def test_one_header_covers_every_object_in_the_column(test_contexts):
    """
    The array form's header spans the whole entry, not one object.

    Entry 1 holds two objects, each with two strings, so the column is one
    `fNBytes + fVersion` header plus four counted strings: the byte count is
    the rest of the entry. A per-object header would leave the count short.
    """
    branch = _branch(test_contexts, "m_objs/m_objs.m_tstr[2]")
    basket = branch.basket(0)
    offsets = basket.byte_offsets
    assert offsets is not None, "the fixture must store entry offsets"

    raw = basket.data.tobytes()
    start, stop = int(offsets[1]), int(offsets[2])
    entry = raw[start:stop]

    byte_count, version = struct.unpack(">Ih", entry[:6])
    assert byte_count & kByteCountMask
    assert byte_count & ~kByteCountMask == len(entry) - 4
    assert version == 10

    # Four strings of seven bytes each ("t1_0_0" and friends) follow the header.
    assert len(entry) - 6 == 4 * 7


def test_the_frame_is_one_per_entry_not_one_per_object(test_contexts):
    """
    Every entry is exactly one header plus `objects × 2` strings.

    With `objects` differing between entries, a per-object header cannot produce
    this pattern.
    """
    branch = _branch(test_contexts, "m_objs/m_objs.m_tstr[2]")
    offsets = [int(x) for x in branch.basket(0).byte_offsets]

    for entry_index in range(3):
        size = offsets[entry_index + 1] - offsets[entry_index]
        # 6 bytes of header, then two counted 7-byte strings per object
        assert size == 6 + _objects_in(entry_index) * 2 * 7
