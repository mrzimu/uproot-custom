"""
The built-in readers, written in the JIT reader API.

These are the same twelve reads as `uproot_custom.python`, kept
separate on purpose: that module stays an independent implementation of the
same format, so a disagreement between the two is a finding rather than a
shared assumption.  What differs is that a reader here declares its buffers,
constants and sub-readers as fields and leaves `read` free of allocation and
of `raise`, which is what lets the JIT compile it.

Buffers are declared with a `struct` typecode (`"i"`, `"q"`, `"d"`,
...), not a NumPy dtype name; `Buf` maps the typecode to the array dtype.

Nothing is interpreted at run time: `read` / `read_many` / `read_until` /
`read_many_memberwise` exist only as source for the frontend, and `data`
runs in Python over the buffers the virtual machine filled.
"""

from __future__ import annotations

from typing import cast

import numpy as np

from uproot_custom.consts import (
    TYPECODE,
    kByteCountMask,
    kClassMask,
    kIsReferenced,
    kMapOffset,
    kNewClassTag,
    kStreamedMemberwise,
)
from uproot_custom.detree.bufferproxy import BufferProxy
from uproot_custom.detree.decl import (
    Buffer,
    Child,
    ChildList,
    Const,
    Reader,
    State,
    Stream,
    reader,
)

#: primitive leaves the frontend may build.  Only the fixed-width codes the VM
#: implements: ``l``/``L`` are platform-dependent in ``array.array`` and have no
#: coercer in the machine, so a buffer must never be declared with them.
_PRIMITIVE_TYPECODES = ("b", "B", "h", "H", "i", "I", "q", "Q", "f", "d")

# Field annotations name what the reader instance actually gets (``Buffer`` ->
# ``BufferProxy``, ``Child`` -> ``Reader``, ...).  The class-body value is still the
# declaration object, so ``cast`` bridges the two for type checkers; the
# declaration is what ``Reader.__init_subclass__`` consumes and removes.


@reader
class PrimitiveReader(Reader):
    """
    A leaf of a built-in type; the value is read into a buffer of its own.
    """

    typecode = cast(TYPECODE, Const("i", type=str, choices=_PRIMITIVE_TYPECODES))
    values = cast(BufferProxy, Buffer(from_const="typecode"))

    def read(self, stream: Stream):
        stream.read_into(self.values)

    def data(self):
        return np.asarray(self.values)


@reader
class TObjectReader(Reader):
    """
    The `TObject` base, read for its header and (optionally) its bytes.
    """

    keep_data = cast(bool, Const(False, type=bool))
    unique_id = cast(BufferProxy, Buffer("i"))
    bits = cast(BufferProxy, Buffer("I"))
    pidf = cast(BufferProxy, Buffer("H"))
    pidf_offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))

    def read(self, stream: Stream):
        stream.skip_fVersion()
        unique_id = stream.read_int32()
        bits = stream.read_uint32()

        if bits & kIsReferenced:
            if self.keep_data:
                self.pidf.append(stream.read_uint16())
            else:
                stream.skip(2)

        if self.keep_data:
            self.unique_id.append(unique_id)
            self.bits.append(bits)
            self.pidf_offsets.append(len(self.pidf))

    def data(self):
        if not self.keep_data:
            return None
        return (
            np.asarray(self.unique_id),
            np.asarray(self.bits),
            np.asarray(self.pidf),
            np.asarray(self.pidf_offsets),
        )


@reader
class TStringReader(Reader):
    """
    A length-prefixed byte string: `TString`, or a header-less one.
    """

    with_header: bool = cast(bool, Const(False, type=bool))
    offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))
    chars = cast(BufferProxy, Buffer("B"))

    def _body(self, stream: Stream):
        size = stream.read_uint8()
        if size == 255:
            size = stream.read_uint32()
        stream.read_bulk(self.chars, size)
        self.offsets.append(len(self.chars))

    def read(self, stream: Stream):
        self._body(stream)

    def read_many(self, stream, count):
        if count == 0:
            return 0
        if self.with_header:
            stream.skip_fNBytes()
            stream.skip_fVersion()
        for _ in range(count):
            self._body(stream)
        return count

    def read_until(self, stream, end_pos):
        if stream.cursor == end_pos:
            return 0
        if self.with_header:
            stream.skip_fNBytes()
            stream.skip_fVersion()
        count = 0
        while stream.cursor < end_pos:
            self._body(stream)
            count += 1
        return count

    def data(self):
        return np.asarray(self.offsets), np.asarray(self.chars)


@reader
class STLStringReader(Reader):
    """
    A `std::string`, which keeps its size before the characters.
    """

    with_header: bool = cast(bool, Const(False, type=bool))
    offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))
    chars = cast(BufferProxy, Buffer("B"))

    def _body(self, stream: Stream):
        size = stream.read_uint8()
        if size == 255:
            size = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + size)
        stream.read_bulk(self.chars, size)

    def read(self, stream: Stream):
        if self.with_header:
            stream.skip_fNBytes()
            stream.skip_fVersion()
        self._body(stream)

    def read_many(self, stream, count):
        if count == 0:
            return 0
        if self.with_header:
            stream.skip_fNBytes()
            stream.skip_fVersion()
        for _ in range(count):
            self._body(stream)
        return count

    def read_until(self, stream, end_pos):
        if stream.cursor == end_pos:
            return 0
        if self.with_header:
            stream.skip_fNBytes()
            stream.skip_fVersion()
        count = 0
        while stream.cursor < end_pos:
            self._body(stream)
            count += 1
        return count

    def data(self):
        return np.asarray(self.offsets), np.asarray(self.chars)


@reader
class TArrayReader(Reader):
    """
    A `TArray`/`std::array`: a `uint32` size then a bulk read.
    """

    typecode = cast(TYPECODE, Const("i", type=str, choices=_PRIMITIVE_TYPECODES))
    offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))
    values = cast(BufferProxy, Buffer(from_const="typecode"))

    def read(self, stream: Stream):
        size = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + size)
        stream.read_bulk(self.values, size)

    def data(self):
        return np.asarray(self.offsets), np.asarray(self.values)


@reader
class STLSeqReader(Reader):
    """
    A sequence-like STL container (`vector`, `list`, `set`, ...).
    """

    with_header: bool = cast(bool, Const(True, type=bool))
    offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))
    element: Reader = cast(Reader, Child())

    def _element_version(self, stream: Stream):
        version = stream.read_fVersion()
        if version == 0:
            stream.skip(4)

    def _body(self, stream, is_memberwise):
        size = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + size)
        if is_memberwise:
            self.element.read_many_memberwise(stream, size)
        else:
            self.element.read_many(stream, size)

    def read(self, stream: Stream):
        stream.skip_fNBytes()
        version = stream.read_fVersion()
        is_memberwise = bool(version & kStreamedMemberwise)
        if is_memberwise:
            self._element_version(stream)
        self._body(stream, is_memberwise)

    def read_many(self, stream, count):
        if count == 0:
            return 0
        is_memberwise = False
        if self.with_header:
            stream.skip_fNBytes()
            version = stream.read_fVersion()
            is_memberwise = bool(version & kStreamedMemberwise)
        if is_memberwise:
            self._element_version(stream)
        for _ in range(count):
            self._body(stream, is_memberwise)
        return count

    def read_until(self, stream, end_pos):
        if stream.cursor == end_pos:
            return 0
        is_memberwise = False
        if self.with_header:
            stream.skip_fNBytes()
            version = stream.read_fVersion()
            is_memberwise = bool(version & kStreamedMemberwise)
        if is_memberwise:
            self._element_version(stream)
        count = 0
        while stream.cursor < end_pos:
            self._body(stream, is_memberwise)
            count += 1
        return count

    def data(self):
        return np.asarray(self.offsets), self.element.data()


@reader
class STLMapReader(Reader):
    """
    A mapping-like STL container; keys and values are separate buffers.
    """

    with_header: bool = cast(bool, Const(True, type=bool))
    offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))
    key: Reader = cast(Reader, Child())
    value: Reader = cast(Reader, Child())

    def _element_version(self, stream: Stream):
        # Deliberately unconditional: the python backend has always read it,
        # and a reader must see the same bytes either way.
        version = stream.read_fVersion()
        if version == 0:
            stream.skip(4)

    def _body(self, stream, is_memberwise):
        size = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + size)
        if is_memberwise:
            self.key.read_many(stream, size)
            self.value.read_many(stream, size)
        else:
            for _ in range(size):
                self.key.read(stream)
                self.value.read(stream)

    def read(self, stream: Stream):
        stream.skip_fNBytes()
        version = stream.read_fVersion()
        self._element_version(stream)
        self._body(stream, bool(version & kStreamedMemberwise))

    def read_many(self, stream, count):
        if count == 0:
            return 0
        is_memberwise = False
        if self.with_header:
            stream.skip_fNBytes()
            version = stream.read_fVersion()
            is_memberwise = bool(version & kStreamedMemberwise)
            self._element_version(stream)
        for _ in range(count):
            self._body(stream, is_memberwise)
        return count

    def read_until(self, stream, end_pos):
        if stream.cursor == end_pos:
            return 0
        is_memberwise = False
        if self.with_header:
            stream.skip_fNBytes()
            version = stream.read_fVersion()
            is_memberwise = bool(version & kStreamedMemberwise)
            self._element_version(stream)
        count = 0
        while stream.cursor < end_pos:
            self._body(stream, is_memberwise)
            count += 1
        return count

    def data(self):
        return np.asarray(self.offsets), self.key.data(), self.value.data()


@reader
class GroupReader(Reader):
    """
    Several readers over one object, in declaration order.
    """

    elements: tuple[Reader, ...] = cast(tuple[Reader, ...], ChildList())

    def read(self, stream: Stream):
        for element in self.elements:
            element.read(stream)

    def read_many_memberwise(self, stream, count):
        assert count >= 0, "read_many_memberwise with a negative count"
        for element in self.elements:
            element.read_many(stream, count)
        return count

    def data(self):
        return [element.data() for element in self.elements]


@reader
class AnyClassReader(Reader):
    """
    Any object framed by its byte count, which the read must consume exactly.
    """

    elements: tuple[Reader, ...] = cast(tuple[Reader, ...], ChildList())

    def read(self, stream: Stream):
        nbytes = stream.read_fNBytes()
        start_pos = stream.cursor
        end_pos = start_pos + nbytes

        version = stream.read_fVersion()
        if version == 0:
            stream.skip(4)

        for element in self.elements:
            element.read(stream)

        assert stream.cursor == end_pos, "the read did not consume the byte count"

    def read_many_memberwise(self, stream, count):
        assert count >= 0, "read_many_memberwise with a negative count"
        for element in self.elements:
            element.read_many(stream, count)
        return count

    def data(self):
        return [element.data() for element in self.elements]


@reader
class AnyPointerReader(Reader):
    """
    A pointer written by `TBuffer::WriteObjectAny`.

    The tag decides what follows: nothing (a null pointer), a back reference, a
    new class name, or a new object of a class already named.  Class names and
    object indexes survive across events, so they are declared as state.
    """

    element = cast(Reader, Child())
    object_counter = cast(int, State(int, 0))
    class_name = cast(str, State(str, ""))
    object_indexes = cast(BufferProxy, Buffer("q"))

    def read(self, stream: Stream):
        start_pos = stream.cursor
        ref_begin = start_pos + stream.initial_cursor_position
        fNBytes = stream.read_uint32()

        if (fNBytes & kByteCountMask) == 0 or fNBytes == kNewClassTag:
            fVersion = 0
            ref_begin = 0
            fTag = fNBytes
            fNBytes = 0
        else:
            fVersion = 1
            fTag = stream.read_uint32()
            fNBytes = fNBytes & ~kByteCountMask

        end_pos = start_pos + 4 + fNBytes if fVersion > 0 else start_pos + 4

        if (fTag & kClassMask) == 0:
            if fTag == 0:
                assert stream.cursor == end_pos, "a null pointer reads no bytes"
                self.object_indexes.append(-1)
                return
            assert fTag != 1, "kAnyP (tag == 1) is not supported"
            if not stream.has_ref(fTag):
                stream.cursor = end_pos
                return
            self.object_indexes.append(stream.ref_object_index(fTag))
            assert stream.cursor == end_pos, "a back reference reads no bytes"
            return

        if fTag == kNewClassTag:
            new_name = stream.read_null_terminated_string()
            if not self.class_name:
                self.class_name = new_name
            else:
                stream.check_class_name(self.class_name, new_name)
            if fVersion > 0:
                stream.set_class_ref(ref_begin + kMapOffset, new_name)
            else:
                stream.set_class_ref(stream.ref_count() + 1, new_name)
        else:
            cls_ref_key = fTag & ~kClassMask
            if stream.has_ref(cls_ref_key):
                stream.check_class_name(self.class_name, stream.ref_class_name(cls_ref_key))

        self.element.read(stream)
        self.object_indexes.append(self.object_counter)
        if fVersion > 0:
            stream.set_object_ref(ref_begin + kMapOffset, self.object_counter)
        else:
            stream.set_object_ref(stream.ref_count() + 1, self.object_counter)
        self.object_counter = self.object_counter + 1

        assert stream.cursor == end_pos, "the read did not consume the byte count"

    def data(self):
        return self.element.data(), np.asarray(self.object_indexes)


@reader
class CStyleArrayReader(Reader):
    """
    A C-style array, sized by the streamer info or by the entry boundary.
    """

    flat_size = cast(int, Const(-1, type=int, ge=-1))
    offsets = cast(BufferProxy, Buffer("q", init=(0,), kind="offsets"))
    element = cast(Reader, Child())

    def read(self, stream: Stream):
        if self.flat_size >= 0:
            self.element.read_many(stream, self.flat_size)
        else:
            end_pos = stream.next_offset_after(stream.cursor)
            count = self.element.read_until(stream, end_pos)
            self.offsets.append(self.offsets[-1] + count)

    def read_many(self, stream, count):
        assert self.flat_size >= 0, "a jagged CStyleArray cannot be read in bulk"
        assert count >= 0, "read_many with a negative count"
        for _ in range(count):
            self.element.read_many(stream, self.flat_size)
        return count

    def read_until(self, stream, end_pos):
        assert False, "CStyleArray.read_until is not supported"

    def data(self):
        if self.flat_size >= 0:
            return self.element.data()
        return np.asarray(self.offsets), self.element.data()


@reader
class EmptyReader(Reader):
    """
    Reads nothing; used where a member's value is not wanted.
    """

    def read(self, stream: Stream):
        pass

    def data(self):
        return None


__all__ = [
    "AnyClassReader",
    "AnyPointerReader",
    "CStyleArrayReader",
    "EmptyReader",
    "GroupReader",
    "PrimitiveReader",
    "STLMapReader",
    "STLSeqReader",
    "STLStringReader",
    "TArrayReader",
    "TObjectReader",
    "TStringReader",
]
