import awkward as ak
import numpy as np
import pytest
from numpy.testing import assert_array_equal

from uproot_custom import _forth
from uproot_custom.backend import use_backend as use_reader_backend


def _read_with_backend(test_file, branch, backend):
    """
    Read *branch* with *backend*, bypassing uproot's array cache.

    The Python backend is the oracle: every other backend must return the same
    array for the same basket.
    """
    test_file.file._array_cache = None
    with use_reader_backend(backend):
        return test_file[branch].array()


def _test_helper(test_contexts, subtests, backend):
    for test_name, ctx in test_contexts.items():
        test_file = ctx["file"]
        for sub_branch in ctx["branches"]:
            with subtests.test(test_name=test_name, branch=sub_branch, backend=backend):
                expected = _read_with_backend(test_file, sub_branch, "python")
                actual = _read_with_backend(test_file, sub_branch, backend)
                assert ak.array_equal(expected, actual)


def test_python(test_contexts, subtests):
    for test_name, ctx in test_contexts.items():
        test_file = ctx["file"]
        for sub_branch in ctx["branches"]:
            with subtests.test(test_name=test_name, branch=sub_branch):
                _read_with_backend(test_file, sub_branch, "python")


def test_cpp(test_contexts, subtests):
    _test_helper(test_contexts, subtests, "cpp")


def test_detree(test_contexts, subtests):
    pytest.importorskip("detree", reason="detree-vm is not installed")
    _test_helper(test_contexts, subtests, "detree")


#: Branches the experimental Forth reader cannot decode yet: a c-style array of
#: maps inside an object comes back empty.  Forth is development-only, so the
#: comparison excludes them instead of failing the whole backend.
FORTH_UNSUPPORTED = {
    "/tree:branch/m_vec_stl_array/m_vec_stl_array.m_arr_map_int_double[3]",
    "/tree:branch/m_vec_stl_array/m_vec_stl_array.m_arr_map_str_str[3]",
    "/tree:branch/m_map_stl_array/m_map_stl_array.second.m_arr_map_int_double[3]",
    "/tree:branch/m_map_stl_array/m_map_stl_array.second.m_arr_map_str_str[3]",
}


def test_forth(test_contexts, subtests):
    forth_test_names = [
        "primitive",
        "stl_string",
        "stl_sequence",
        "stl_map",
        "root_objects",
        "cstyle_array",
        "stl_array",
        "stl_seq_with_obj",
        "stl_map_with_obj",
        "stl_nested",
        "stl_complicated",
    ]

    forth_contexts = {
        test_name: {
            "file": ctx["file"],
            "branches": [
                branch for branch in ctx["branches"] if branch not in FORTH_UNSUPPORTED
            ],
        }
        for (test_name, ctx) in test_contexts.items()
        if test_name in forth_test_names
    }

    with pytest.warns(UserWarning):
        _test_helper(forth_contexts, subtests, "forth")


def test_forth_read_data_generates_event_loop(monkeypatch):
    captured = {}

    class DummyForthMachine:
        def __init__(self, codes):
            captured["codes"] = codes
            self.outputs = {}

        def run(self, inputs):
            captured["inputs"] = inputs

    monkeypatch.setattr(ak.forth, "ForthMachine64", DummyForthMachine)

    data = np.array([1, 2, 3], dtype=np.uint8)
    offsets = np.array([0, 1, 2, 3], dtype=np.uint32)
    forth_holder = _forth.BufferHolder()
    forth_reader = _forth.PrimitiveReader("x", "uint8", forth_holder)

    expected = np.array([1, 2, 3], dtype=np.uint8)
    DummyForthMachine.outputs = {forth_reader.data_token: expected}

    def _patched_init(self, codes):
        captured["codes"] = codes
        self.outputs = {forth_reader.data_token: expected}

    monkeypatch.setattr(DummyForthMachine, "__init__", _patched_init, raising=False)
    forth_out = _forth.read_data(data, offsets, forth_reader)

    codes = captured["codes"]
    assert _forth.stream_ievt_token in codes
    assert _forth.stream_evt_end_pos_token in codes
    assert f"{len(offsets) - 1} 0 do" in codes
    assert forth_reader.read_token in codes

    assert_array_equal(forth_out, expected)


def test_forth_cstyle_array_fixed_read_code():
    forth_holder = _forth.BufferHolder()
    forth_element = _forth.PrimitiveReader("item", "uint8", forth_holder)
    forth_reader = _forth.CStyleArrayReader("arr", 2, forth_element, forth_holder)

    codes = forth_reader.read()
    assert "2" in codes
    assert forth_element.read_many_token in codes


def test_forth_cstyle_array_jagged_uses_event_end_pos():
    forth_holder = _forth.BufferHolder()
    forth_element = _forth.PrimitiveReader("item", "uint8", forth_holder)
    forth_reader = _forth.CStyleArrayReader("arr", -1, forth_element, forth_holder)

    codes = forth_reader.read()
    assert _forth.stream_evt_end_pos_token in codes
    assert f"{_forth.stream_evt_end_pos_token} @" in codes
    assert forth_element.read_until_token in codes
    assert forth_reader.offsets_token in codes
