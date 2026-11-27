from __future__ import annotations

import numpy as np
import pytest

from uproot_custom.element_info import ElementFrame, ElementInfo
from uproot_custom.utils import get_stl_value_version_min


def _info(**kwargs):
    """Build one element the way `uproot` hands it over."""
    base = {
        "fName": "m",
        "fTypeName": "int",
        "fType": 3,
        "fArrayLength": 0,
        "fArrayDim": 0,
        "fMaxIndex": np.asarray([0, 0, 0, 0, 0], dtype=">i4"),
    }
    base.update(kwargs)
    return ElementInfo.from_streamer_info(base)


def test_a_scalar_has_no_array_form():
    info = _info()
    assert not info.is_array
    assert info.element_count is None
    assert info.dims == ()
    assert info.frame is ElementFrame.NONE


def test_a_basic_array_takes_its_count_from_f_array_length():
    info = _info(fArrayLength=2, fArrayDim=1, fMaxIndex=np.asarray([2, 0, 0, 0, 0]))
    assert info.is_array
    assert info.element_count == 2
    assert info.dims == (2,)


def test_a_multidimensional_array_keeps_every_extent():
    info = _info(
        fArrayLength=24,
        fArrayDim=3,
        fMaxIndex=np.asarray([2, 3, 4, 0, 0]),
    )
    assert info.element_count == 24
    assert info.dims == (2, 3, 4)


def test_f_array_length_wins_over_the_extent_product():
    # A disagreement no real file shows; the specification names one of them
    # as the authority, so the other must not be able to override it.
    info = _info(fArrayLength=6, fArrayDim=1, fMaxIndex=np.asarray([2, 0, 0, 0, 0]))
    assert info.element_count == 6


def test_a_pre_6_24_array_recovers_its_rank_from_the_extents():
    # ROOT before 6.24/02 did not copy `fArrayDim` into the temporary element
    # (`StreamerInfo.md` §10), so the count survives and the rank does not.
    info = _info(fArrayLength=4, fArrayDim=0, fMaxIndex=np.asarray([4, 0, 0, 0, 0]))
    assert info.is_array
    assert info.element_count == 4
    assert info.dims == (4,)


def test_a_pre_6_24_array_without_extents_is_one_dimensional():
    info = _info(fArrayLength=4, fArrayDim=0, fMaxIndex=np.asarray([0, 0, 0, 0, 0]))
    assert info.dims == (4,)


@pytest.mark.parametrize(
    ("f_type", "frame"),
    [
        (3, ElementFrame.NONE),
        (65, ElementFrame.NONE),
        (66, ElementFrame.NONE),
        (85, ElementFrame.SHARED),
        (86, ElementFrame.SHARED),
        (87, ElementFrame.SHARED),
        (500, ElementFrame.SHARED),
        (61, ElementFrame.OBJECT),
        (62, ElementFrame.OBJECT),
        (81, ElementFrame.OBJECT),
        (82, ElementFrame.OBJECT),
        (63, ElementFrame.OBJECT),
        (64, ElementFrame.OBJECT),
        (68, ElementFrame.OBJECT),
        (69, ElementFrame.OBJECT),
    ],
)
def test_the_frame_follows_the_element_code(f_type, frame):
    assert _info(fType=f_type).frame is frame


def test_a_base_element_is_not_an_array():
    # `fMaxIndex[1]` of a base holds `fBaseCheckSum`, not an extent
    # (`StreamerInfo.md` §9), so nothing may read it as one.
    info = _info(
        fType=66,
        fTypeName="BASE",
        fMaxIndex=np.asarray([0, -1877229523, 0, 0, 0], dtype=">i4"),
    )
    assert not info.is_array
    assert info.element_count is None
    # Nothing may read `fMaxIndex` as an extent: the checksum sits there, so the
    # extents are empty rather than `(-1877229523,)`.
    assert info.dims == ()


def test_a_synthetic_element_carries_only_a_name_and_a_type_name():
    info = ElementInfo.from_streamer_info({"fName": "e", "fTypeName": "vector<int>"})
    assert info.ftype is None
    assert not info.is_array
    assert info.frame is ElementFrame.NONE


@pytest.mark.parametrize(
    ("f_type", "expected"),
    [(500, 8), (501, 9), (None, 8)],
)
def test_the_frame_version_that_carries_the_value_version(f_type, expected):
    # `kSTL` reads the value class's version from frame version 8 and `kSTLp`,
    # a pointer to the same container, only from 9
    # (`TStreamerInfoReadBuffer.cxx`, the `kSTL` and `kSTLp` cases).
    assert get_stl_value_version_min(f_type) == expected
