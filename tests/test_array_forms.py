"""
A fixed array and a `std::array` of the same element type are the same bytes.

ROOT maps `std::array<T,N>` to a C array before writing the streamer info, so
nothing on disk tells the two apart and nothing needs to (`Collections.md` §11).
What the bytes do say is how the run of elements is framed, and that is decided
by the element class alone (`ElementTypes.md` §7.2).

The expectations here are the values `TArrayForms::fill` writes, checked against
a hand decode of the basket bytes and confirmed by reading the file back with
ROOT (`TArrayForms` through `SetBranchAddress`). `uproot` cannot read most of
these forms -- its `AsStridedObjects` does not know the shared header -- so it is
not the oracle for this file.
"""

from __future__ import annotations

import awkward as ak
import pytest

#: Each member of `TArrayForms`, in its two spellings.
PAIRS = [
    ("m_carr_int[2]", "m_arr_int[2]"),
    ("m_carr_tstr[2]", "m_arr_tstr[2]"),
    ("m_carr_str[2]", "m_arr_str[2]"),
    ("m_carr_vec[2]", "m_arr_vec[2]"),
    ("m_carr_mapvec[2]", "m_arr_mapvec[2]"),
    ("m_carr_tobj[2]", "m_arr_tobj[2]"),
    ("m_carr_tnamed[2]", "m_arr_tnamed[2]"),
]


def _array(test_contexts, branch):
    test_file = test_contexts["array_forms"]["file"]
    test_file.file._array_cache = None
    return test_file["tree"][branch].array(library="ak")


@pytest.mark.parametrize(("c_array", "std_array"), PAIRS)
def test_both_spellings_have_the_same_layout(test_contexts, c_array, std_array):
    """
    Same framing, so the same awkward type; only the contents differ.

    Comparing the arrays themselves would compare two different sets of values:
    the fixture fills the two spellings differently on purpose, so a mixed-up
    column cannot pass.
    """
    assert str(ak.type(_array(test_contexts, c_array))) == str(
        ak.type(_array(test_contexts, std_array))
    )


def _expected(i):
    """
    The values `fill(i)` writes, one entry each.
    """
    base = 10 * i
    return {
        "m_carr_int[2]": [base, base + 1],
        "m_arr_int[2]": [base + 100, base + 101],
        "m_carr_tstr[2]": [f"ct0_{i}", f"ct1_{i}"],
        "m_arr_tstr[2]": [f"at0_{i}", f"at1_{i}"],
        "m_carr_str[2]": [f"cs0_{i}", f"cs1_{i}"],
        "m_arr_str[2]": [f"as0_{i}", f"as1_{i}"],
        "m_carr_vec[2]": [[base, base + 1], [base + 1, base + 2]],
        "m_arr_vec[2]": [[base + 100], [base + 101]],
        "m_carr_mapvec[2]": [
            [{"key": 0, "val": [base, base + 1]}],
            [{"key": 1, "val": [base + 1, base + 2]}],
        ],
        "m_arr_mapvec[2]": [
            [{"key": 0, "val": [base + 100]}],
            [{"key": 1, "val": [base + 101]}],
        ],
        # A `TObject` and a `TNamed` hold nothing but these fields, so the two
        # spellings are given different values on purpose: the layout is the
        # same, and only the contents can catch a mixed-up column.
        "m_carr_tobj[2]": [
            {"fUniqueID": 1000 * i + j + 1, "fBits": 0, "pidf": []} for j in (0, 1)
        ],
        "m_arr_tobj[2]": [
            {"fUniqueID": 1000 * i + 100 + j + 1, "fBits": 0, "pidf": []} for j in (0, 1)
        ],
        "m_carr_tnamed[2]": [{"fName": f"cn{j}_{i}", "fTitle": ""} for j in (0, 1)],
        "m_arr_tnamed[2]": [{"fName": f"an{j}_{i}", "fTitle": ""} for j in (0, 1)],
    }


@pytest.mark.parametrize("entry", [0, 3])
@pytest.mark.parametrize("branch", sorted(_expected(0)))
def test_the_values_are_the_ones_that_went_in(test_contexts, branch, entry):
    array = _array(test_contexts, branch)
    assert ak.to_list(array[entry]) == _expected(entry)[branch]
