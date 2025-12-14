from __future__ import annotations

import os
import shutil
import struct
import textwrap
from array import array
from typing import Any, Callable, Literal

import numpy as np
from numpy.typing import NDArray

kNewClassTag = 0xFFFFFFFF
kByteCountMask = 0x40000000
kIsReferenced = 1 << 4
kStreamedMemberwise = 1 << 14


def debug_print(*args, **kwargs):
    pass


if "UPROOT_DEBUG" in os.environ:
    debug_print = print


class BinaryBuffer:
    def __init__(
        self,
        data: NDArray[np.uint8],
        offsets: NDArray[np.uint32],
        repr_nbytes: int = 50,
    ):
        self.data = data
        self.offsets = offsets
        self.cursor = 0
        self.repr_nbytes = repr_nbytes

    @property
    def entries(self):
        return len(self.offsets) - 1

    @property
    def remaining_data(self):
        return self.data[self.cursor :]

    def read_uint8(self) -> int:
        val = struct.unpack_from(">B", self.remaining_data)[0]
        self.cursor += 1
        return val

    def read_uint16(self) -> int:
        val = struct.unpack_from(">H", self.remaining_data)[0]
        self.cursor += 2
        return val

    def read_uint32(self) -> int:
        val = struct.unpack_from(">I", self.remaining_data)[0]
        self.cursor += 4
        return val

    def read_uint64(self) -> int:
        val = struct.unpack_from(">Q", self.remaining_data)[0]
        self.cursor += 8
        return val

    def read_int8(self) -> int:
        val = struct.unpack_from(">b", self.remaining_data)[0]
        self.cursor += 1
        return val

    def read_int16(self) -> int:
        val = struct.unpack_from(">h", self.remaining_data)[0]
        self.cursor += 2
        return val

    def read_int32(self) -> int:
        val = struct.unpack_from(">i", self.remaining_data)[0]
        self.cursor += 4
        return val

    def read_int64(self) -> int:
        val = struct.unpack_from(">q", self.remaining_data)[0]
        self.cursor += 8
        return val

    def read_float(self) -> float:
        val = struct.unpack_from(">f", self.remaining_data)[0]
        self.cursor += 4
        return val

    def read_double(self) -> float:
        val = struct.unpack_from(">d", self.remaining_data)[0]
        self.cursor += 8
        return val

    def read_bool(self) -> bool:
        return bool(self.read_uint8())

    def read_fNBytes(self) -> np.uint32:
        byte_count = self.read_uint32()
        assert byte_count & kByteCountMask, f"Invalid byte count: {byte_count}"
        return byte_count & (~kByteCountMask)

    def read_fVersion(self):
        return self.read_int16()

    def read_null_terminated_string(self):
        start = self.cursor
        while self.data[self.cursor] != 0:
            self.cursor += 1
        return self.data[start : self.cursor].tobytes().decode()

    def read_obj_header(self):
        self.read_fNBytes()
        fTag = self.read_uint32()
        if fTag == kNewClassTag:
            return self.read_null_terminated_string()
        else:
            return ""

    def read_TString(self):
        length = self.read_uint8()
        if length == 255:
            length = self.read_uint32()

        start = self.cursor
        self.cursor += length
        return self.data[start : self.cursor].tobytes().decode()

    def skip(self, n: int):
        self.cursor += n

    def skip_fNBytes(self):
        self.read_fNBytes()

    def skip_fVersion(self):
        self.skip(2)

    def skip_null_terminated_string(self):
        while self.data[self.cursor] != 0:
            self.cursor += 1

    def skip_obj_header(self):
        self.skip_fNBytes()
        fTag = self.read_uint32()
        if fTag == kNewClassTag:
            self.skip_null_terminated_string()

    def skip_TObject(self):
        self.skip_fVersion()
        self.skip(4)  # fUniqueID
        fBits = self.read_uint32()
        if fBits & kIsReferenced:
            self.skip(2)  # pidf

    def __repr__(self):
        res = ""
        data_view = self.data[self.cursor : self.cursor + self.repr_nbytes]

        for i in data_view:
            res += f"{i:3d}, "

        if len(data_view) < len(self.data[self.cursor :]):
            res += "..."
        else:
            res = res[:-1]

        width = 76
        try:
            width, _ = shutil.get_terminal_size()
            width = max(40, width - 4)
        except:
            # Ignore errors if terminal size cannot be determined; use default width
            pass

        wrapper = textwrap.TextWrapper(
            width=width,
            initial_indent="[ ",
            subsequent_indent=" ",
            break_long_words=False,
            break_on_hyphens=False,
            drop_whitespace=False,
            replace_whitespace=False,
        )

        return "BinaryBuffer:\n" + wrapper.fill(res) + "]"


class IReader:
    def __init__(self, name: str):
        self.name = name

    def read(self, buffer: BinaryBuffer) -> None:
        raise NotImplementedError

    def data(self) -> Any:
        raise NotImplementedError

    def read_many(self, buffer: BinaryBuffer, count: int) -> int:
        for _ in range(count):
            self.read(buffer)
        return count

    def read_until(self, buffer: BinaryBuffer, end_pos: int) -> int:
        count = 0
        while buffer.cursor < end_pos:
            self.read(buffer)
            count += 1
        return count

    def read_many_memberwise(self, buffer: BinaryBuffer, count: int) -> int:
        raise NotImplementedError


DTYPE_TO_TYPECODE = {
    "u1": "B",
    "u2": "H",
    "u4": "I",
    "u8": "Q",
    "i1": "b",
    "i2": "h",
    "i4": "i",
    "i8": "q",
    "f": "f",
    "d": "d",
    "bool": "B",
}

DTYPE_TO_READER: dict[str, Callable[[BinaryBuffer], int]] = {
    "u1": BinaryBuffer.read_uint8,
    "u2": BinaryBuffer.read_uint16,
    "u4": BinaryBuffer.read_uint32,
    "u8": BinaryBuffer.read_uint64,
    "i1": BinaryBuffer.read_int8,
    "i2": BinaryBuffer.read_int16,
    "i4": BinaryBuffer.read_int32,
    "i8": BinaryBuffer.read_int64,
    "f": BinaryBuffer.read_float,
    "d": BinaryBuffer.read_double,
    "bool": BinaryBuffer.read_bool,
}


class PrimitiveReader(IReader):
    def __init__(
        self,
        name: str,
        dtype: Literal[
            "bool", "u1", "u2", "u4", "u8", "i1", "i2", "i4", "i8", "float", "double"
        ],
    ):
        super().__init__(name)
        self.dtype = dtype
        self.typecode = DTYPE_TO_TYPECODE[dtype]
        self._data = array(self.typecode)
        self.buffer_reader = DTYPE_TO_READER[dtype]

    def read(self, buffer):
        self._data.append(self.buffer_reader(buffer))

    def data(self):
        return np.frombuffer(self._data.tobytes(), dtype=self.dtype)


class TObjectReader(IReader):
    def __init__(self, name: str, keep_data: bool = False):
        super().__init__(name)

        self.keep_data = keep_data
        self.unique_id = array("i")
        self.bits = array("I")
        self.pidf = array("H")
        self.pidf_offsets = array("q", [0])

    def read(self, buffer):
        buffer.skip_fVersion()
        fUniqueID = buffer.read_int32()
        fBits = buffer.read_uint32()

        if fBits & kIsReferenced:
            if self.keep_data:
                self.pidf.append(buffer.read_uint16())
            else:
                buffer.skip(2)

        if self.keep_data:
            self.unique_id.append(fUniqueID)
            self.bits.append(fBits)
            self.pidf_offsets.append(len(self.pidf))

    def data(self):
        if not self.keep_data:
            return None

        unique_id_array = np.frombuffer(self.unique_id.tobytes(), dtype="i4")
        bits_array = np.frombuffer(self.bits.tobytes(), dtype="u4")
        pidf_array = np.frombuffer(self.pidf.tobytes(), dtype="u2")
        pidf_offsets_array = np.frombuffer(self.pidf_offsets.tobytes(), dtype="i8")
        return unique_id_array, bits_array, pidf_array, pidf_offsets_array


class TStringReader(IReader):
    def __init__(self, name: str, with_header: bool):
        super().__init__(name)
        self.with_header = with_header

        self._data = array("B")
        self.offsets = array("q", [0])

    def read(self, buffer):
        fSize = buffer.read_uint8()
        if fSize == 255:
            fSize = buffer.read_uint32()

        for _ in range(fSize):
            self._data.append(buffer.read_uint8())
        self.offsets.append(len(self._data))

    def read_many(self, buffer, count):
        assert (
            count >= 0
        ), f"Calling {self.name}.read_many with negative count: {count} is not allowed"

        if count == 0:
            return 0

        if self.with_header:
            buffer.skip_fNBytes()
            buffer.skip_fVersion()

        for _ in range(count):
            self.read(buffer)

    def read_until(self, buffer, end_pos):
        if buffer.cursor == end_pos:
            return 0

        if self.with_header:
            buffer.skip_fNBytes()
            buffer.skip_fVersion()

        count = 0
        while buffer.cursor < end_pos:
            self.read(buffer)
            count += 1
        return count

    def data(self):
        data_array = np.frombuffer(self._data.tobytes(), dtype="u1")
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="i8")
        return offsets_array, data_array


class STLSeqReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
        objwise_or_memberwise: Literal["auto", "obj-wise", "member-wise"],
        element_reader: IReader,
    ):
        super().__init__(name)

        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.element_reader = element_reader
        self.offsets = array("q", [0])

    def check_objwise_memberwise(self, is_memberwise: bool):
        if self.objwise_or_memberwise == "obj-wise" and is_memberwise:
            raise ValueError(
                f"STLMapReader({self.name}) expected obj-wise reading but got member-wise"
            )

        if self.objwise_or_memberwise == "member-wise" and not is_memberwise:
            raise ValueError(
                f"STLMapReader({self.name}) expected member-wise reading but got obj-wise"
            )

    def read_body(self, buffer: BinaryBuffer, is_memberwise: bool):
        fSize = buffer.read_uint32()
        self.offsets.append(self.offsets[-1] + fSize)

        debug_print(
            f"STLSeqReader({self.name}): reading body, is_memberwise={is_memberwise}, fSize={fSize}\n"
        )
        debug_print(buffer)

        if is_memberwise:
            self.element_reader.read_many_memberwise(buffer, fSize)
        else:
            self.element_reader.read_many(buffer, fSize)

    def read(self, buffer):
        buffer.skip_fNBytes()

        fVersion = buffer.read_fVersion()
        is_memberwise = bool(fVersion & kStreamedMemberwise)
        self.check_objwise_memberwise(is_memberwise)

        if is_memberwise:
            buffer.skip(2)

        self.read_body(buffer, is_memberwise)

    def read_many(self, buffer, count):
        if count == 0:
            return 0

        elif count < 0:
            assert (
                self.with_header
            ), f"STLSeqReader({self.name}).read_many called with negative count expecting with_header=True"

            fNBytes = buffer.read_fNBytes()
            end_pos = buffer.cursor + fNBytes

            fVersion = buffer.read_fVersion()
            is_memberwise = bool(fVersion & kStreamedMemberwise)
            self.check_objwise_memberwise(is_memberwise)

            if is_memberwise:
                buffer.skip(2)

            cur_count = 0
            while buffer.cursor < end_pos:
                self.read_body(buffer, is_memberwise)
                cur_count += 1
            return cur_count

        else:
            is_memberwise = self.objwise_or_memberwise == "member-wise"
            if self.with_header:
                buffer.skip_fNBytes()
                fVersion = buffer.read_fVersion()
                is_memberwise = bool(fVersion & kStreamedMemberwise)
                self.check_objwise_memberwise(is_memberwise)

            if is_memberwise:
                buffer.skip(2)

            for _ in range(count):
                self.read_body(buffer, is_memberwise)
            return count

    def read_until(self, buffer, end_pos):
        if buffer.cursor == end_pos:
            return 0

        is_membersie = self.objwise_or_memberwise == "member-wise"

        if self.with_header:
            buffer.skip_fNBytes()
            fVersion = buffer.read_fVersion()
            is_membersie = bool(fVersion & kStreamedMemberwise)
            self.check_objwise_memberwise(is_membersie)

        if is_membersie:
            buffer.skip(2)

        count = 0
        while buffer.cursor < end_pos:
            self.read_body(buffer, is_membersie)
            count += 1
        return count

    def data(self):
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="i8")
        element_data = self.element_reader.data()
        return offsets_array, element_data


class STLMapReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
        objwise_or_memberwise: Literal["auto", "obj-wise", "member-wise"],
        key_reader: IReader,
        value_reader: IReader,
    ):
        super().__init__(name)

        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.key_reader = key_reader
        self.value_reader = value_reader
        self.offsets = array("q", [0])

    def check_objwise_memberwise(self, is_memberwise: bool):
        if self.objwise_or_memberwise == "obj-wise" and is_memberwise:
            raise ValueError(
                f"STLMapReader({self.name}) expected obj-wise reading but got member-wise"
            )

        if self.objwise_or_memberwise == "member-wise" and not is_memberwise:
            raise ValueError(
                f"STLMapReader({self.name}) expected member-wise reading but got obj-wise"
            )

    def read_body(self, buffer: BinaryBuffer, is_memberwise: bool):
        fSize = buffer.read_uint32()
        self.offsets.append(self.offsets[-1] + fSize)

        debug_print(
            f"STLMapReader({self.name}): reading body, is_memberwise={is_memberwise}, fSize={fSize}\n"
        )
        debug_print(buffer)

        if is_memberwise:
            self.key_reader.read_many(buffer, fSize)
            self.value_reader.read_many(buffer, fSize)
        else:
            for _ in range(fSize):
                self.key_reader.read(buffer)
                self.value_reader.read(buffer)

    def read(self, buffer):
        buffer.skip_fNBytes()
        fVersion = buffer.read_fVersion()
        buffer.skip(6)

        is_memberwise = bool(fVersion & kStreamedMemberwise)
        self.check_objwise_memberwise(is_memberwise)
        self.read_body(buffer, is_memberwise)

    def read_many(self, buffer, count):
        if count == 0:
            return 0

        elif count < 0:
            assert (
                self.with_header
            ), f"STLMapReader({self.name}).read_many called with negative count expecting with_header=True"

            fNBytes = buffer.read_fNBytes()
            end_pos = buffer.cursor + fNBytes

            fVersion = buffer.read_fVersion()
            buffer.skip(6)

            is_memberwise = bool(fVersion & kStreamedMemberwise)
            self.check_objwise_memberwise(is_memberwise)

            cur_count = 0
            while buffer.cursor < end_pos:
                self.read_body(buffer, is_memberwise)
                cur_count += 1
            return cur_count

        else:
            is_memberwise = self.objwise_or_memberwise == "member-wise"
            if self.with_header:
                buffer.skip_fNBytes()
                fVersion = buffer.read_fVersion()
                buffer.skip(6)

                is_memberwise = bool(fVersion & kStreamedMemberwise)
                self.check_objwise_memberwise(is_memberwise)

            for _ in range(count):
                self.read_body(buffer, is_memberwise)
            return count

    def read_until(self, buffer, end_pos):
        if buffer.cursor == end_pos:
            return 0

        is_membersie = self.objwise_or_memberwise == "member-wise"

        if self.with_header:
            buffer.skip_fNBytes()
            fVersion = buffer.read_fVersion()
            buffer.skip(6)

            is_membersie = bool(fVersion & kStreamedMemberwise)
            self.check_objwise_memberwise(is_membersie)

        count = 0
        while buffer.cursor < end_pos:
            self.read_body(buffer, is_membersie)
            count += 1
        return count

    def read_many_memberwise(self, buffer, count):
        assert (
            count >= 0
        ), f"Calling {self.name}.read_many_memberwise with negative count: {count} is not allowed"

        is_memberwise = True

        self.check_objwise_memberwise(is_memberwise)
        return self.read_many(buffer, count)

    def data(self):
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="i8")
        key_data = self.key_reader.data()
        value_data = self.value_reader.data()
        return offsets_array, key_data, value_data


class STLStringReader(IReader):
    def __init__(self, name: str, with_header: bool):
        super().__init__(name)
        self.with_header = with_header

        self._data = array("B")
        self.offsets = array("q", [0])

    def read_body(self, buffer: BinaryBuffer):
        fSize = buffer.read_uint8()
        if fSize == 255:
            fSize = buffer.read_uint32()

        self.offsets.append(self.offsets[-1] + fSize)
        for _ in range(fSize):
            self._data.append(buffer.read_uint8())

    def read(self, buffer):
        if self.with_header:
            buffer.skip_fNBytes()
            buffer.skip_fVersion()
        self.read_body(buffer)

    def read_many(self, buffer, count):
        if count == 0:
            return 0

        elif count < 0:
            assert (
                self.with_header
            ), f"STLStringReader({self.name}).read_many called with negative count expecting with_header=True"

            fNBytes = buffer.read_fNBytes()
            end_pos = buffer.cursor + fNBytes

            buffer.skip_fVersion()

            cur_count = 0
            while buffer.cursor < end_pos:
                self.read_body(buffer)
                cur_count += 1
            return cur_count

        else:
            if self.with_header:
                buffer.skip_fNBytes()
                buffer.skip_fVersion()

            for _ in range(count):
                self.read_body(buffer)
            return count

    def read_until(self, buffer, end_pos):
        if buffer.cursor == end_pos:
            return 0

        if self.with_header:
            buffer.skip_fNBytes()
            buffer.skip_fVersion()

        count = 0
        while buffer.cursor < end_pos:
            self.read_body(buffer)
            count += 1
        return count

    def data(self):
        data_array = np.frombuffer(self._data.tobytes(), dtype="u1")
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="i8")
        return offsets_array, data_array


class TArrayReader(IReader):
    def __init__(
        self,
        name: str,
        dtype: Literal["i1", "i2", "i4", "i8", "float", "double"],
    ):
        super().__init__(name)
        self.dtype = dtype
        self.typecode = DTYPE_TO_TYPECODE[dtype]
        self._data = array(self.typecode)
        self.offsets = array("q", [0])
        self.buffer_reader = DTYPE_TO_READER[dtype]

    def read(self, buffer):
        fSize = buffer.read_uint32()
        self.offsets.append(self.offsets[-1] + fSize)

        for _ in range(fSize):
            self._data.append(self.buffer_reader(buffer))

    def data(self):
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="i8")
        data_array = np.frombuffer(self._data.tobytes(), dtype=self.dtype)
        return offsets_array, data_array


class GroupReader(IReader):
    def __init__(self, name: str, element_readers: list[IReader]):
        super().__init__(name)
        self.element_readers = element_readers

    def read(self, buffer):
        for reader in self.element_readers:
            debug_print(f"GroupReader({self.name}) reading element {reader.name}:\n")
            debug_print(buffer)
            reader.read(buffer)

    def read_many_memberwise(self, buffer, count):
        assert (
            count >= 0
        ), f"Calling {self.name}.read_many_memberwise with negative count: {count} is not allowed"

        for reader in self.element_readers:
            debug_print(
                f"GroupReader{self.name} reading many member-wise element {reader.name}:\n"
            )
            debug_print(buffer)
            reader.read_many(buffer, count)

        return count

    def data(self):
        return [reader.data() for reader in self.element_readers]


class AnyClassReader(IReader):
    def __init__(self, name: str, element_readers: list[IReader]):
        super().__init__(name)
        self.element_readers = element_readers

    def read(self, buffer: BinaryBuffer):
        fNBytes = buffer.read_fNBytes()
        start_pos = buffer.cursor
        end_pos = start_pos + fNBytes

        buffer.skip_fVersion()

        for reader in self.element_readers:
            debug_print(f"AnyClassReader({self.name}) reading element {reader.name}:\n")
            debug_print(buffer)
            reader.read(buffer)

        assert buffer.cursor == end_pos, (
            f"AnyClassReader({self.name}): Invalid read length! Expect {fNBytes} bytes, "
            f"but read {buffer.cursor - start_pos} bytes."
        )

    def read_many_memberwise(self, buffer, count):
        assert (
            count >= 0
        ), f"Calling {self.name}.read_many_memberwise with negative count: {count} is not allowed"

        for reader in self.element_readers:
            debug_print(
                f"AnyClassReader{self.name} reading many member-wise element {reader.name}:\n"
            )
            debug_print(buffer)
            reader.read_many(buffer, count)

        return count

    def data(self):
        return [reader.data() for reader in self.element_readers]


class ObjectHeaderReader(IReader):
    def __init__(self, name: str, element_reader: IReader):
        super().__init__(name)
        self.element_reader = element_reader

    def read(self, buffer):
        fNBytes = buffer.read_fNBytes()
        start_pos = buffer.cursor
        end_pos = buffer.cursor + fNBytes

        fTag = buffer.read_int32()
        if fTag == kNewClassTag:
            buffer.skip_null_terminated_string()

        self.element_reader.read(buffer)

        assert buffer.cursor == end_pos, (
            f"ObjectHeaderReader({self.name}): Invalid read length! Expect {fNBytes} bytes, "
            f"but read {buffer.cursor - start_pos} bytes."
        )

    def data(self):
        return self.element_reader.data()


class CStyleArrayReader(IReader):
    def __init__(self, name: str, flat_size: int, element_reader: IReader):
        super().__init__(name)
        self.flat_size = flat_size
        self.element_reader = element_reader
        self.offsets = array("q", [0])

    def read(self, buffer):
        debug_print(
            f"CStyleArrayReader({self.name}): reading C-style array of flat_size={self.flat_size}\n"
        )
        debug_print(buffer)

        if self.flat_size >= 0:
            self.element_reader.read_many(buffer, self.flat_size)

        else:
            entry_offsets = buffer.offsets
            cursor_pos = buffer.cursor
            end_offset_index = (entry_offsets > cursor_pos).nonzero()[0].min()
            end_pos = entry_offsets[end_offset_index]

            count = self.element_reader.read_until(buffer, end_pos)
            self.offsets.append(self.offsets[-1] + count)
            debug_print(f"CStyleArrayReader({self.name}): read {count} elements")

    def read_many(self, buffer, count):
        assert (
            self.flat_size >= 0
        ), f"Calling CStyleArrayReader({self.name}).read_many with negative flat_size is not allowed"

        assert (
            count >= 0
        ), f"Calling CStyleArrayReader({self.name}).read_many with negative count: {count} is not allowed"

        for _ in range(count):
            self.element_reader.read_many(buffer, self.flat_size)

        return count

    def read_until(self, buffer, end_pos):
        raise NotImplementedError("CStyleArrayReader.read_until is not supported")

    def data(self):
        if self.flat_size >= 0:
            return self.element_reader.data()
        else:
            offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="i8")
            element_data = self.element_reader.data()
            return offsets_array, element_data


class EmptyReader(IReader):
    def read(self, buffer):
        pass

    def data(self):
        return None


def read_data(data: NDArray[np.uint8], offsets: NDArray[np.uint32], reader: IReader):
    buffer = BinaryBuffer(data, offsets)
    for i_evt in range(buffer.entries):
        start_pos = buffer.cursor
        reader.read(buffer)
        end_pos = buffer.cursor

        assert end_pos == offsets[i_evt + 1], (
            f"read_data: Invalid read length for {reader.name} at entry {i_evt}! Expect "
            f"{buffer.offsets[i_evt + 1]-buffer.offsets[i_evt]} bytes, but read {end_pos - start_pos} bytes."
        )

    return reader.data()
