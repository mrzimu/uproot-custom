"""
The Python backend's `BinaryStream`: counted regions.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from uproot_custom.consts import kByteCountMask
from uproot_custom.python import BinaryStream


def _stream(payload: bytes) -> BinaryStream:
    data = np.frombuffer(payload, dtype=np.uint8)
    offsets = np.array([0, len(payload)], dtype=np.uint32)
    return BinaryStream(data, offsets, 0)


def test_a_counted_region_checks_its_end():
    stream = _stream(struct.pack(">I", 4 | kByteCountMask) + struct.pack(">i", 7))

    with stream.check_nbytes():
        assert stream.read_int32() == 7

    assert stream.open_frames == 0


def test_counted_regions_nest():
    payload = (
        struct.pack(">I", 8 | kByteCountMask)
        + struct.pack(">I", 4 | kByteCountMask)
        + struct.pack(">i", 7)
    )
    stream = _stream(payload)

    with stream.check_nbytes(), stream.check_nbytes():
        assert stream.read_int32() == 7

    assert stream.open_frames == 0


def test_the_explicit_pair_checks_the_end():
    stream = _stream(struct.pack(">I", 4 | kByteCountMask) + struct.pack(">i", 7))

    stream.check_nbytes_start()
    assert stream.open_frames == 1
    assert stream.read_int32() == 7
    stream.check_nbytes_end()

    assert stream.open_frames == 0


def test_a_wrong_byte_count_names_both_positions():
    stream = _stream(struct.pack(">I", 8 | kByteCountMask) + struct.pack(">i", 7))

    with pytest.raises(AssertionError, match=r"expected 12, got 8"):  # noqa: SIM117
        with stream.check_nbytes():
            stream.read_int32()


def test_an_explicit_end_is_checked_without_a_frame():
    stream = _stream(struct.pack(">ii", 1, 2))
    stream.read_int32()

    stream.check_nbytes_end(4)

    with pytest.raises(AssertionError, match=r"expected 8, got 4"):
        stream.check_nbytes_end(8)


def test_an_end_without_a_start_is_an_error():
    stream = _stream(b"")

    with pytest.raises(AssertionError, match="without check_nbytes_start"):
        stream.check_nbytes_end()


def test_a_raising_block_leaves_no_open_frame():
    stream = _stream(struct.pack(">I", 4 | kByteCountMask) + struct.pack(">i", 7))

    with pytest.raises(RuntimeError, match="boom"), stream.check_nbytes():
        raise RuntimeError("boom")

    assert stream.open_frames == 0
