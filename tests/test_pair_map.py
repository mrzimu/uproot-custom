"""
A map is a run of pairs, and a pair is a class with its own streamer info.

ROOT records a `TStreamerInfo` for `pair<K,V>` in any file that holds a map,
whose two elements `first` and `second` are the key and the value
(`TGenCollectionProxy.cxx`, `GetValueClass`), and the memberwise form of a map
is those two elements read as two columns
(`TStreamerInfoReadBuffer.cxx`, the `kSTL` case).  A pair that is not part of a
map is the same class read the same way, which is what `m_vecvecpair` checks.

`uproot` cannot read the two fixed arrays -- its object reader does not know the
shared header of a run of maps -- so the values here are the ones
`TPairMap::fill` writes, confirmed by reading the same file back with ROOT.
"""

from __future__ import annotations

import awkward as ak
import pytest

from uproot_custom.utils import find_class_streamer_info


def _array(test_contexts, branch):
    test_file = test_contexts["pair_map"]["file"]
    return test_file["tree"][branch].array(library="ak")


def _named(i, k):
    return {"fName": f"n{i}_{k}", "fTitle": ""}


def _expected(i):
    """
    The values `TPairMap::fill(i)` writes, one entry each.

    The three inner runs hold `1 + i % 3` maps, so an entry that reused the
    previous entry's header would show up here.
    """
    count = 1 + i % 3
    return {
        "m_mapvstr[2]": [
            [{"key": "k0", "val": [f"v{100 * i}"]}],
            [{"key": "k1", "val": [f"v{100 * i + 1}"]}],
        ],
        "m_mapnamed[2]": [
            [{"key": 0, "TNamed": _named(i, 0)}],
            [{"key": 1, "TNamed": _named(i, 1)}],
        ],
        "m_vecmapvstr": [[{"key": f"k{k}", "val": [f"v{100 * i + k}"]}] for k in range(count)],
        "m_vecmapnamed": [[{"key": k, "TNamed": _named(i, k)}] for k in range(count)],
        "m_vecvecpair": [[{"first": 100 * i + k, "second": 0.5 * k}] for k in range(count)],
    }


@pytest.mark.parametrize("entry", [0, 1, 3])
@pytest.mark.parametrize("branch", sorted(_expected(0)))
def test_the_values_are_the_ones_that_went_in(test_contexts, branch, entry):
    array = _array(test_contexts, branch)
    assert ak.to_list(array[entry]) == _expected(entry)[branch]


@pytest.mark.parametrize("branch", ["m_vecmapvstr", "m_vecmapnamed", "m_vecvecpair"])
def test_the_inner_run_has_one_map_per_element(test_contexts, branch):
    """
    The run length is the map's own count, not the previous entry's.

    A reader that read the count once for the whole column would pass
    `test_the_values_are_the_ones_that_went_in` for entry 0 alone.
    """
    array = _array(test_contexts, branch)
    assert [len(row) for row in ak.to_list(array)] == [1 + i % 3 for i in range(10)]


def test_a_pair_standing_on_its_own_is_the_same_class_as_a_map_element(test_contexts):
    """
    Both are read from the file's `pair<int,double>` streamer info.

    That is what makes `m_vecvecpair` work at all: nothing in the map's type
    name describes a pair that is not inside a map.
    """
    array = _array(test_contexts, "m_vecvecpair")
    assert ak.fields(array.layout.content.content) == ["first", "second"]


def test_a_streamer_info_is_found_through_the_spelling_the_file_uses():
    """
    ROOT writes a space before the closing brackets when a parameter is itself
    a template, so the name has to be compared with whitespace removed.
    """
    all_streamer_info = {"pair<int,map<int,string> >": [{"fName": "first"}]}

    found = find_class_streamer_info("pair<int,map<int,string>>", all_streamer_info)

    assert found is not None
    name, elements = found
    assert name == "pair<int,map<int,string> >"
    assert elements == [{"fName": "first"}]


def test_a_class_without_a_streamer_info_is_not_found():
    """
    A pair that no streamer info describes falls back to the map's type name.
    """
    assert find_class_streamer_info("pair<int,double>", {}) is None
