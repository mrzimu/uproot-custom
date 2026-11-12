from __future__ import annotations

import struct
from bisect import bisect_right
from contextlib import contextmanager

from uproot_custom.consts import kByteCountMask, kIsReferenced, kNewClassTag
from uproot_custom.detree.bufferproxy import BufferProxy

#: The one context manager a read path may use; the frontend knows it by name.
COUNTED_CONTEXT = "check_nbytes"


class Stream:
    """
    A byte buffer with a cursor, the entry offsets and the object references.
    """

    def __init__(self, data: bytes, offsets: list[int], initial_cursor_position: int = 0):
        self.data = data
        self.offsets = offsets
        self.cursor = 0
        self.initial_cursor_position = initial_cursor_position

        #: tag -> ``("object", index)`` or ``("class", name)``
        self.refs = {}

        #: end positions of the open counted regions, innermost last
        self._nbytes_marks = []

    def __repr__(self):
        return f"Stream(cursor={self.cursor}/{len(self.data)})"

    @property
    def entries(self):
        return len(self.offsets) - 1

    # -- scalars ----------------------------------------------------------
    def _read(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.cursor + size > len(self.data):
            raise IndexError(f"read of {size} bytes past the end of the basket")
        value = struct.unpack_from(">" + fmt, self.data, self.cursor)
        self.cursor += size
        return value

    def read_uint8(self):
        return self._read("B")[0]

    def read_uint16(self):
        return self._read("H")[0]

    def read_uint32(self):
        return self._read("I")[0]

    def read_uint64(self):
        return self._read("Q")[0]

    def read_int8(self):
        return self._read("b")[0]

    def read_int16(self):
        return self._read("h")[0]

    def read_int32(self):
        return self._read("i")[0]

    def read_int64(self):
        return self._read("q")[0]

    def read_float(self):
        return self._read("f")[0]

    def read_double(self):
        return self._read("d")[0]

    def read_bool(self):
        return bool(self.read_uint8())

    def read_into(self, buffer: BufferProxy):
        """
        Read one value of buffer's own dtype and append it.
        """
        buffer.append(self._read(buffer.typecode)[0])

    def read_bulk(self, buffer: BufferProxy, count: int):
        """
        Read count values of buffer's typecode, in one extend.
        """
        if count <= 0:
            return

        fmt = buffer.typecode * count
        buffer.extend(self._read(fmt))

    # -- the ROOT header fields -------------------------------------------
    def read_fNBytes(self):
        value = self.read_uint32()
        assert value & kByteCountMask, f"fNBytes={value:#x} lacks kByteCountMask"
        return value & ~kByteCountMask

    # -- counted regions ---------------------------------------------------
    def check_nbytes_start(self):
        """
        Read a masked `fNBytes` and remember where the counted region ends.

        The call opens a frame and `check_nbytes_end` closes it.  Frames nest,
        so a sub-reader that is framed itself does not disturb its caller.
        """
        nbytes = self.read_fNBytes()
        self._nbytes_marks.append(self.cursor + nbytes)

    def check_nbytes_end(self, expected: int | None = None):
        """
        Fail unless the cursor is at the end of the counted region.

        Args:
            expected: the end position, for a region whose size the caller
                computed instead of reading; the innermost frame is then left
                open, so the two forms do not pair with each other.
        """
        if expected is None:
            if not self._nbytes_marks:
                raise AssertionError("check_nbytes_end() without check_nbytes_start()")
            expected = self._nbytes_marks.pop()
        if self.cursor != expected:
            raise AssertionError(
                "the read did not end at the byte count "
                f"(expected {expected}, got {self.cursor})"
            )

    @contextmanager
    def check_nbytes(self):
        """
        Frame the block with a masked `fNBytes`, checked on exit.
        """
        self.check_nbytes_start()
        try:
            yield
        except BaseException:
            self._nbytes_marks.pop()
            raise
        self.check_nbytes_end()

    @property
    def open_frames(self):
        """
        The number of counted regions still waiting for their end.
        """
        return len(self._nbytes_marks)

    def read_fVersion(self):
        return self.read_int16()

    def read_null_terminated_string(self):
        start = self.cursor
        limit = len(self.data)
        while self.cursor < limit and self.data[self.cursor] != 0:
            self.cursor += 1
        if self.cursor >= limit:
            self.cursor = start
            raise IndexError("unterminated string")
        value = self.data[start : self.cursor].decode()
        self.cursor += 1
        return value

    def skip(self, nbytes):
        if self.cursor + nbytes > len(self.data):
            raise IndexError(f"skip of {nbytes} bytes past the end of the basket")
        self.cursor += nbytes

    def skip_fNBytes(self):
        value = self.read_uint32()
        assert value & kByteCountMask, f"fNBytes={value:#x} lacks kByteCountMask"

    def skip_fVersion(self):
        self.skip(2)

    def skip_null_terminated_string(self):
        limit = len(self.data)
        while self.cursor < limit and self.data[self.cursor] != 0:
            self.cursor += 1
        if self.cursor >= limit:
            raise IndexError("unterminated string")
        self.cursor += 1

    def skip_obj_header(self):
        self.skip_fNBytes()
        if self.read_uint32() == kNewClassTag:
            self.skip_null_terminated_string()

    def skip_TObject(self):
        self.skip_fVersion()
        self.skip(4)  # fUniqueID
        bits = self.read_uint32()
        if bits & kIsReferenced:
            self.skip(2)  # pidf

    # -- the basket -------------------------------------------------------
    def next_offset_after(self, pos: int):
        """
        Smallest entry offset strictly greater than pos.
        """
        index = bisect_right(self.offsets, pos)
        if index >= len(self.offsets):
            raise IndexError(f"no entry offset after {pos}")
        return self.offsets[index]

    # -- object references ------------------------------------------------
    def has_ref(self, tag):
        return tag in self.refs

    def ref_object_index(self, tag):
        """
        The object index of an object reference; -1 for a class one.
        """
        entry = self.refs.get(tag)
        if entry is None:
            return 0
        return entry[1] if entry[0] == "object" else -1

    def ref_class_name(self, tag):
        """
        The class name of a class reference; None otherwise.
        """
        entry = self.refs.get(tag)
        if entry is None or entry[0] != "class":
            return None
        return entry[1]

    def set_object_ref(self, tag, object_index: int):
        self.refs[tag] = ("object", object_index)

    def set_class_ref(self, tag, class_name: str):
        self.refs[tag] = ("class", class_name)

    def ref_count(self):
        return len(self.refs)

    def check_class_name(self, expected: str, actual: str):
        assert expected == actual, (
            f"inconsistent class names for multiple objects: "
            f"expected {expected!r}, got {actual!r}"
        )
