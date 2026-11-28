"""
The frame version at which an STL element carries its value class's version.

A collection reads it from frame version 8 and a pointer to one only from 9
(`TStreamerInfoReadBuffer.cxx`, the `kSTL` and `kSTLp` cases).  The file does
not distinguish the two in `fType`, which is 500 (`kStreamer`) for every
`TStreamerSTL` whether the member is a pointer or not (`StreamerInfo.md` §10);
the pointer is marked by a type name ending in `*` (`Collections.md` §11.3).
"""

from __future__ import annotations

import pytest

from uproot_custom.consts import (
    STL_VERSION_WITH_VALUE_VERSION,
    STL_VERSION_WITH_VALUE_VERSION_POINTER,
)
from uproot_custom.factories import STLMapFactory, STLSeqFactory
from uproot_custom.utils import get_stl_value_version_min


@pytest.mark.parametrize(
    ("f_type_name", "expected"),
    [
        ("vector<int>", STL_VERSION_WITH_VALUE_VERSION),
        ("vector<int>*", STL_VERSION_WITH_VALUE_VERSION_POINTER),
        ("vector<int> *", STL_VERSION_WITH_VALUE_VERSION_POINTER),
        (None, STL_VERSION_WITH_VALUE_VERSION),
    ],
)
def test_the_frame_version_that_carries_the_value_version(f_type_name, expected):
    # A pointer to a collection has the same `fType` as the collection itself,
    # so only the type name can tell them apart.
    streamer_info = {"fName": "m", "fType": 500}
    if f_type_name is not None:
        streamer_info["fTypeName"] = f_type_name

    assert get_stl_value_version_min(streamer_info) == expected


@pytest.mark.parametrize(
    ("factory", "top_type_name", "f_type_name"),
    [
        (STLSeqFactory, "vector", "vector<int>"),
        (STLSeqFactory, "vector", "vector<int>*"),
        (STLMapFactory, "map", "map<int,double>"),
        (STLMapFactory, "map", "map<int,double>*"),
    ],
)
def test_the_factory_takes_the_boundary_from_the_element(factory, top_type_name, f_type_name):
    """
    A member declared as a pointer to a collection is read by this factory.

    The pointer carries no tag of its own on disk (`Collections.md` §11.3), so
    the frame version that carries the value class's version is the only thing
    that differs from the collection itself.
    """
    info = {"fName": "m", "fTypeName": f_type_name, "fType": 500}

    built = factory.build_factory(top_type_name, info, {}, "")

    expected = (
        STL_VERSION_WITH_VALUE_VERSION_POINTER
        if f_type_name.rstrip().endswith("*")
        else STL_VERSION_WITH_VALUE_VERSION
    )
    assert built.value_version_min == expected
