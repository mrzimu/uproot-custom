import pytest

pytest.importorskip("numba")

import numpy as np

import uproot_custom
import uproot_custom.factories
from uproot_custom.readers._numba import Stream


class TestStream:
    def test_read_primitives(self):
        dtypes = [
            (np.uint8, Stream.read_uint8),
            (np.int8, Stream.read_int8),
            (np.uint16, Stream.read_uint16),
            (np.int16, Stream.read_int16),
            (np.uint32, Stream.read_uint32),
            (np.int32, Stream.read_int32),
            (np.uint64, Stream.read_uint64),
            (np.int64, Stream.read_int64),
            (np.float32, Stream.read_float),
            (np.float64, Stream.read_double),
        ]

        for dtype, method in dtypes:
            data = np.array([1, 2, 3, 4], dtype=dtype).byteswap(inplace=True).view(np.uint8)
            stream = Stream(data, np.array([0], dtype=np.int64))
            for expected in [1, 2, 3, 4]:
                assert method(stream) == expected

    def test_read_null_terminated_string(self):
        test_str = "hello numba!"
        data = np.frombuffer(test_str.encode("utf-8") + b"\x00", dtype=np.uint8)
        stream = Stream(data, np.array([0], dtype=np.int64))
        assert stream.read_null_terminated_string() == test_str


def test_AsCustom_numba_arrays(
    f_test_data, test_branches_inner_backend, subtests, monkeypatch
):
    monkeypatch.setattr(uproot_custom.factories, "reader_backend", "numba")
    assert uproot_custom.factories.reader_backend == "numba"

    with pytest.warns(UserWarning):
        for sub_branch_path in test_branches_inner_backend:
            with subtests.test(sub_branch_path=sub_branch_path):
                f_test_data[sub_branch_path].array()


def test_AsCustom_numba_virtual(
    f_test_data, test_branches_inner_backend, subtests, monkeypatch
):
    monkeypatch.setattr(uproot_custom.factories, "reader_backend", "numba")
    assert uproot_custom.factories.reader_backend == "numba"

    for sub_branch_path in test_branches_inner_backend:
        with subtests.test(sub_branch_path=sub_branch_path):
            f_test_data[sub_branch_path].arrays(virtual=True)
