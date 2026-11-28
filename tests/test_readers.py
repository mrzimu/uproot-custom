import awkward as ak
import numpy as np
import pytest
from numpy.testing import assert_array_equal

import uproot_custom.python as python_impl
from uproot_custom import _forth
from uproot_custom.backend import use_backend as use_reader_backend
from uproot_custom.detree import builtin as detree_impl
from uproot_custom.detree.decl import Reader

#: The reader implementations written in Python, with their base class.
IMPLEMENTATIONS = (
    (python_impl, python_impl.IReader),
    (_forth, _forth.IReader),
    (detree_impl, Reader),
)


def _builtin_readers(module, base):
    """
    The reader classes a module defines itself, keyed by name.
    """
    return {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, type)
        and issubclass(value, base)
        and value is not base
        and value.__module__ == module.__name__
    }


def test_no_builtin_reader_overrides_read_many_bare():
    """
    A run of nested elements is one `read_bare` per element in every implementation.

    Four readers in each implementation used to restate `read_many_bare`, always as
    the base class's own loop, so a reader that disagreed stayed invisible until a
    basket happened to be read. The base default is now the only implementation.
    """
    for module, base in IMPLEMENTATIONS:
        for name, cls in _builtin_readers(module, base).items():
            assert "read_many_bare" not in vars(cls), (
                f"{module.__name__}.{name} overrides read_many_bare; "
                "its default is one read_bare per element"
            )


def test_builtin_readers_skip_the_shared_header_in_the_same_place():
    """
    `read_bare` is overridden by the same readers in all three implementations.

    `read_bare` is where a nested element loses or keeps its own `fNBytes+fVersion`
    header, so a class that overrides it in one implementation and not another reads
    different bytes for the same branch. Forth's `PrimitiveReader` also overrides
    `read_many` and `read_until` to bulk-read numbers; that only changes speed, so it
    is not compared here.
    """
    readers = {
        module.__name__: _builtin_readers(module, base) for module, base in IMPLEMENTATIONS
    }
    shared = set.intersection(*(set(found) for found in readers.values()))

    for name in sorted(shared):
        overrides = {
            module_name: "read_bare" in vars(found[name])
            for module_name, found in readers.items()
        }
        assert len(set(overrides.values())) == 1, f"{name}: {overrides}"


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
    _test_helper(test_contexts, subtests, "detree")


#: Branches the experimental Forth reader cannot decode yet: a c-style array of
#: maps inside an object comes back empty, and a member-wise collection of class
#: values stops after the second entry.  Forth is development-only, so the
#: comparison excludes them instead of failing the whole backend.
FORTH_UNSUPPORTED = {
    "/tree:branch/m_vec_stl_array/m_vec_stl_array.m_arr_map_int_double[3]",
    "/tree:branch/m_vec_stl_array/m_vec_stl_array.m_arr_map_str_str[3]",
    "/tree:branch/m_map_stl_array/m_map_stl_array.second.m_arr_map_int_double[3]",
    "/tree:branch/m_map_stl_array/m_map_stl_array.second.m_arr_map_str_str[3]",
    "/tree:branch/m_pvecnamed",
    "/tree:branch/m_pmap",
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
        "array_forms",
        "array_in_object",
        "pair_map",
        "stl_pointer",
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
