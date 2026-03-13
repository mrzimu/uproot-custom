import sys
import textwrap
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

import black
import numba as nb
import numba.typed
import numba.types
import numpy as np
from numba.experimental import jitclass

if sys.version_info > (3, 9):
    DTYPE: TypeAlias = Literal[
        "bool", "u1", "u2", "u4", "u8", "i1", "i2", "i4", "i8", "float", "double"
    ]
else:
    DTYPE = Literal["bool", "u1", "u2", "u4", "u8", "i1", "i2", "i4", "i8", "float", "double"]

_dtype_to_numbatype = {
    "bool": "numba.types.uint8",
    "u1": "numba.types.uint8",
    "u2": "numba.types.uint16",
    "u4": "numba.types.uint32",
    "u8": "numba.types.uint64",
    "i1": "numba.types.int8",
    "i2": "numba.types.int16",
    "i4": "numba.types.int32",
    "i8": "numba.types.int64",
    "float": "numba.types.float32",
    "double": "numba.types.float64",
}

kNewClassTag = 0xFFFFFFFF
kByteCountMask = 0x40000000
kIsReferenced = 1 << 4
kStreamedMemberwise = 1 << 14


def _typedlist_to_array_func(dtype):
    @nb.njit
    def func(typed_list):
        return np.asarray(typed_list, dtype=dtype)

    return func


list_to_array_uint8 = _typedlist_to_array_func(np.uint8)
list_to_array_uint16 = _typedlist_to_array_func(np.uint16)
list_to_array_uint32 = _typedlist_to_array_func(np.uint32)
list_to_array_uint64 = _typedlist_to_array_func(np.uint64)
list_to_array_int8 = _typedlist_to_array_func(np.int8)
list_to_array_int16 = _typedlist_to_array_func(np.int16)
list_to_array_int32 = _typedlist_to_array_func(np.int32)
list_to_array_int64 = _typedlist_to_array_func(np.int64)
list_to_array_float32 = _typedlist_to_array_func(np.float32)
list_to_array_float64 = _typedlist_to_array_func(np.float64)


@nb.njit
def _uint8_to_str(data: np.ndarray) -> str:
    res = ""
    for i in data:
        res += chr(i)
    return res


@jitclass(
    [
        ("data", nb.uint8[:]),
        ("offsets", nb.int64[:]),
        ("cursor", nb.int64),
    ]
)
class Stream:
    def __init__(self, data: np.ndarray, offsets: np.ndarray):
        self.data = data
        self.offsets = offsets
        self.cursor = 0

    def check_position(self, i_evt):
        expected_pos = self.offsets[i_evt + 1]
        if self.cursor != expected_pos:
            raise ValueError(
                f"Stream position mismatch: expected {expected_pos} but got {self.cursor} for event {i_evt}"
            )

    @property
    def entries(self):
        return self.offsets.size - 1

    @property
    def remaining_data(self):
        return self.data[self.cursor :]

    def read_uint8(self) -> np.uint8:
        value = self.data[self.cursor]
        self.cursor += 1
        return value

    def read_int8(self) -> np.int8:
        value = self.data[self.cursor : self.cursor + 1].view(np.int8)[0]
        self.cursor += 1
        return value

    def read_uint16(self) -> np.uint16:
        tmp_buffer = np.empty(2, dtype=np.uint8)
        for i in range(2):
            tmp_buffer[1 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.uint16)[0]

    def read_int16(self) -> np.int16:
        tmp_buffer = np.empty(2, dtype=np.uint8)
        for i in range(2):
            tmp_buffer[1 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.int16)[0]

    def read_uint32(self) -> np.uint32:
        tmp_buffer = np.empty(4, dtype=np.uint8)
        for i in range(4):
            tmp_buffer[3 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.uint32)[0]

    def read_int32(self) -> np.int32:
        tmp_buffer = np.empty(4, dtype=np.uint8)
        for i in range(4):
            tmp_buffer[3 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.int32)[0]

    def read_uint64(self) -> np.uint64:
        tmp_buffer = np.empty(8, dtype=np.uint8)
        for i in range(8):
            tmp_buffer[7 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.uint64)[0]

    def read_int64(self) -> np.int64:
        tmp_buffer = np.empty(8, dtype=np.uint8)
        for i in range(8):
            tmp_buffer[7 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.int64)[0]

    def read_float(self) -> np.float32:
        tmp_buffer = np.empty(4, dtype=np.uint8)
        for i in range(4):
            tmp_buffer[3 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.float32)[0]

    def read_double(self) -> np.float64:
        tmp_buffer = np.empty(8, dtype=np.uint8)
        for i in range(8):
            tmp_buffer[7 - i] = self.data[self.cursor]
            self.cursor += 1
        return tmp_buffer.view(np.float64)[0]

    def read_fNBytes(self):
        nbytes = self.read_uint32()
        assert nbytes & kByteCountMask, f"Invalid byte count: {nbytes}"
        return nbytes & (~kByteCountMask)

    def read_fVersion(self):
        return self.read_int16()

    def read_null_terminated_string(self):
        start = self.cursor
        while self.data[self.cursor] != 0:
            self.cursor += 1
        end = self.cursor
        self.cursor += 1  # Skip the null terminator

        return _uint8_to_str(self.data[start:end])

    def read_obj_header(self):
        self.skip_fNBytes()
        fTag = self.read_uint32()
        if fTag == kNewClassTag:
            return self.read_null_terminated_string()
        else:
            return ""

    def read_TString(self):
        fsize = self.read_uint8()
        if fsize == 255:
            fsize = self.read_uint32()

        start = self.cursor
        self.cursor += fsize
        return _uint8_to_str(self.data[start : start + fsize])

    def skip(self, nbytes: int):
        self.cursor += nbytes

    def skip_fNBytes(self):
        self.read_fNBytes()

    def skip_fVersion(self):
        self.skip(2)

    def skip_null_terminated_string(self):
        while self.data[self.cursor] != 0:
            self.cursor += 1
        self.cursor += 1  # Skip the null terminator

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


@dataclass
class CompilationContext:
    buffers: dict[str, np.ndarray] = field(default_factory=dict)  # buffer_id -> numpy_array
    buffer_meta: dict[str, DTYPE] = field(default_factory=dict)  # buffer_id -> dtype

    methods: dict[str, str] = field(default_factory=dict)  # method_id -> method_source
    functions: dict[str, str] = field(default_factory=dict)  # function_id -> function_source

    variables: dict[str, int | float | str | bool] = field(
        default_factory=dict
    )  # variable_id -> variable_value

    constants: dict[str, int | float | str | bool] = field(default_factory=dict)
    compiled_classes: dict[str, object] = field(
        default_factory=dict
    )  # class_id -> compiled_class

    inits: list[str] = field(default_factory=list)  # List of extra init code

    tmp_id_counter: int = 0


class IReader:
    def __init__(self, name: str, context: CompilationContext):
        self.name = name

        self._compilation_context = context

        self.read_id = self.get_attr_id("read")
        self.read_many_id = self.get_attr_id("read_many")
        self.read_until_id = self.get_attr_id("read_until")
        self.read_many_memberwise_id = self.get_attr_id("read_many_memberwise")

    def get_attr_id(self, attr_name: str) -> str:
        tmp_id = self._compilation_context.tmp_id_counter
        self._compilation_context.tmp_id_counter += 1
        return f"{self.__class__.__name__}_{self.name}_{tmp_id}_{attr_name}"

    def declare_buffer(self, buffer_id: str, buffer_type: DTYPE):
        assert (
            buffer_id not in self._compilation_context.buffer_meta
        ), f"Buffer {buffer_id} already declared"

        self._compilation_context.buffer_meta[buffer_id] = buffer_type

    def declare_method(self, method_id: str, method_source: str):
        assert (
            method_id not in self._compilation_context.methods
        ), f"Method {method_id} already declared"

        self._compilation_context.methods[method_id] = method_source

    def declare_function(self, function_id: str, function_source: str):
        assert (
            function_id not in self._compilation_context.functions
        ), f"Function {function_id} already declared"

        self._compilation_context.functions[function_id] = function_source

    def declare_variable(self, variable_id: str, variable_value):
        assert (
            variable_id not in self._compilation_context.variables
        ), f"Variable {variable_id} already declared"

        self._compilation_context.variables[variable_id] = variable_value

    def declare_init(self, init_code: str):
        self._compilation_context.inits.extend((i.strip() for i in init_code.splitlines()))

    def get_buffer(self, buffer_id: str) -> np.ndarray:
        assert (
            buffer_id in self._compilation_context.buffers
        ), f"Buffer {buffer_id} not declared"

        return self._compilation_context.buffers[buffer_id]

    def register_context(self):
        self._compilation_context.inits.append(self.init())
        self.declare_method(self.read_id, self.read())
        self.declare_method(self.read_many_id, self.read_many())
        self.declare_method(self.read_until_id, self.read_until())
        self.declare_method(self.read_many_memberwise_id, self.read_many_memberwise())

    def init(self) -> str:
        return ""

    def read(self) -> str:
        raise NotImplementedError("Subclasses must implement read method")

    def read_many(self) -> str:
        return f"""
        def {self.read_many_id}(self, stream, count):
            for _ in range(count):
                self.{self.read_id}(stream)
        """

    def read_until(self) -> str:
        return f"""
        def {self.read_until_id}(self, stream, end_pos):
            count = 0
            while stream.cursor < end_pos:
                self.{self.read_id}(stream)
                count += 1
            return count
        """

    def read_many_memberwise(self) -> str:
        return f"""
        def {self.read_many_memberwise_id}(self, stream, count):
            raise NotImplementedError(
                f"{self.__class__.__name__}({self.name}).read_many_memberwise is not implemented"
            )
        """

    def data(self):
        raise NotImplementedError("Subclasses must implement data method")


_template = """
import numba
import numba.typed
import numba.types
from numba.experimental import jitclass
from uproot_custom.readers._numba import Stream

{predefines}

{specs}
class {cls_name}:
    def __init__(self):
{init_body}

    def read(self, stream):
        self.{entry_point}(stream)

"""


class Compiler:
    def __init__(
        self,
        cls_name: str,
        reader: IReader,
    ):
        self.context = reader._compilation_context
        self.entry_point = reader.read_id
        self.cls_name = cls_name

        self.reader = reader
        reader.register_context()

    def compile(self):
        init_body, jit_specs_str = self._gen_init()
        constants_src = self._gen_constants()
        methods_src = self._gen_methods()
        functions_src = self._gen_functions()

        class_src = (
            _template.format(
                predefines=constants_src + "\n" + functions_src,
                cls_name=self.cls_name,
                init_body=init_body,
                specs=jit_specs_str,
                entry_point=self.entry_point,
            )
            + methods_src
        )

        return black.format_str(class_src, mode=black.Mode())

    def _gen_constants(self):
        const_src = ""
        for const_id, const_value in self.context.constants.items():
            const_src += f"{const_id} = {repr(const_value)}\n"
        return const_src

    def _gen_methods(self):
        method_src = ""
        for method_body in self.context.methods.values():
            method_src += textwrap.dedent(method_body)
        return textwrap.indent(method_src, " " * 4)

    def _gen_functions(self):
        func_src = ""
        for func_body in self.context.functions.values():
            func_src += textwrap.dedent(func_body)
        return func_src

    def _gen_init(self):
        init_body = ""
        jit_specs = []

        # initialize buffers
        for buffer_id, buffer_dtype in self.context.buffer_meta.items():
            if buffer_dtype not in _dtype_to_numbatype:
                raise ValueError(f"Unsupported buffer dtype: {buffer_dtype}")

            buffer_nbtype = _dtype_to_numbatype[buffer_dtype]
            init_body += f"self.{buffer_id} = numba.typed.List.empty_list({buffer_nbtype})\n"
            jit_specs.append(f'("{buffer_id}", numba.types.ListType({buffer_nbtype}))')

        # initialize variables
        for var_id, var_value in self.context.variables.items():
            if not isinstance(var_value, (int, float, str, bool)):
                raise ValueError(
                    f"Unsupported variable type: {type(var_value)} for variable {var_id}"
                )

            nb_type_name = {
                int: "numba.types.int64",
                float: "numba.types.float64",
                bool: "numba.types.boolean",
                str: "nb.types.string",
            }[type(var_value)]

            init_body += f"self.{var_id} = {repr(var_value)}\n"
            jit_specs.append(f'("{var_id}", {nb_type_name})')

        # generate specs for jitclass
        jit_specs_str = "@jitclass([\n" + ",\n".join(jit_specs) + "\n])\n"

        # extra init code from readers
        for extra_init in self.context.inits:
            init_body += textwrap.dedent(extra_init) + "\n"

        return textwrap.indent(init_body, " " * 8), jit_specs_str


class PrimitiveReader(IReader):
    def __init__(
        self,
        name,
        context,
        dtype: DTYPE,
    ):
        super().__init__(name, context)
        self.dtype = dtype

        self.buffer_id = self.get_attr_id("buffer")
        self.declare_buffer(self.buffer_id, self.dtype)

        self.stream_method = {
            "bool": "read_uint8",
            "u1": "read_uint8",
            "u2": "read_uint16",
            "u4": "read_uint32",
            "u8": "read_uint64",
            "i1": "read_int8",
            "i2": "read_int16",
            "i4": "read_int32",
            "i8": "read_int64",
            "float": "read_float",
            "double": "read_double",
        }[self.dtype]

    def read(self) -> str:
        return f"""
        def {self.read_id}(self, stream):
            self.{self.buffer_id}.append(stream.{self.stream_method}())
        """

    def data(self):
        return self._compilation_context.buffers[self.buffer_id]


class TObjectReader(IReader):
    def __init__(self, name, ctx, keep_data: bool = False):
        super().__init__(name, ctx)

        self.keep_data = keep_data

        self.unique_id_id = self.get_attr_id("unique_id")
        self.bits_id = self.get_attr_id("bits")
        self.pidf_id = self.get_attr_id("pidf")
        self.pidf_offsets_id = self.get_attr_id("pidf_offsets")

        if self.keep_data:
            self.declare_buffer(self.unique_id_id, "i4")
            self.declare_buffer(self.bits_id, "u4")
            self.declare_buffer(self.pidf_id, "u2")
            self.declare_buffer(self.pidf_offsets_id, "i8")
            self.declare_init(f"self.{self.pidf_offsets_id}.append(0)")

    def read(self) -> str:
        read_body = """
        def {read_id}(self, stream):
            stream.skip_fVersion()
            fUniqueID = stream.read_uint32()
            fBits = stream.read_uint32()

            if fBits & {kIsReferenced}:
                if {keep_data}:
                    self.{pidf}.append(stream.read_uint16())
                else:
                    stream.skip(2)

            if {keep_data}:
                self.{unique_id}.append(fUniqueID)
                self.{bits}.append(fBits)
                self.{pidf_offsets}.append(len(self.{pidf}))
        """

        return read_body.format(
            read_id=self.read_id,
            kIsReferenced=kIsReferenced,
            keep_data=self.keep_data,
            unique_id=self.unique_id_id,
            bits=self.bits_id,
            pidf=self.pidf_id,
            pidf_offsets=self.pidf_offsets_id,
        )

    def data(self):
        if not self.keep_data:
            return None

        unique_id_array = self.get_buffer(self.unique_id_id)
        bits_array = self.get_buffer(self.bits_id)
        pidf_array = self.get_buffer(self.pidf_id)
        pidf_offsets_array = self.get_buffer(self.pidf_offsets_id)
        return unique_id_array, bits_array, pidf_array, pidf_offsets_array


class TStringReader(IReader):
    def __init__(self, name, ctx, with_header: bool):
        super().__init__(name, ctx)

        self.with_header = with_header

        self.with_header_id = self.get_attr_id("with_header")
        self.content_id = self.get_attr_id("content")
        self.offsets_id = self.get_attr_id("offsets")

        self.declare_buffer(self.content_id, "u1")
        self.declare_buffer(self.offsets_id, "i8")
        self.declare_init(f"self.{self.offsets_id}.append(0)")

    def read(self):
        read_body = """
        def {read_id}(self, stream):
            fSize = stream.read_uint8()
            if fSize == 255:
                fSize = stream.read_uint32()

            for _ in range(fSize):
                self.{content}.append(stream.read_uint8())
            self.{offsets}.append(len(self.{content}))
        """

        return read_body.format(
            read_id=self.read_id,
            content=self.content_id,
            offsets=self.offsets_id,
        )

    def read_many(self):
        body = """
        def {read_many_id}(self, stream, count):
            assert count >= 0, f"Calling {name}.read_many with negative count {{count}} is not allowed"

            if count == 0:
                return 0

            if {with_header}:
                stream.skip_fNBytes()
                stream.skip_fVersion()

            for _ in range(count):
                self.{read_id}(stream)

            return count
        """

        return body.format(
            read_many_id=self.read_many_id,
            name=self.name,
            with_header=self.with_header,
            read_id=self.read_id,
        )

    def read_until(self):
        body = """
        def {read_until_id}(self, stream, end_pos):
            if stream.cursor == end_pos:
                return 0

            if {with_header}:
                stream.skip_fNBytes()
                stream.skip_fVersion()

            count = 0
            while stream.cursor < end_pos:
                self.{read_id}(stream)
                count += 1
            return count
        """

        return body.format(
            read_until_id=self.read_until_id,
            with_header=self.with_header,
            read_id=self.read_id,
        )

    def data(self):
        offsets = self.get_buffer(self.offsets_id)
        content = self.get_buffer(self.content_id)
        return offsets, content


class STLSeqReader(IReader):
    def __init__(
        self,
        name: str,
        context: CompilationContext,
        with_header: bool,
        objwise_or_memberwise: Literal["auto", "obj-wise", "member-wise"],
        element_reader: IReader,
    ):
        super().__init__(name, context)

        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.element_reader = element_reader

        self.offsets_id = self.get_attr_id("offsets")
        self.read_body_id = self.get_attr_id("read_body")
        self.check_objwise_memberwise_id = self.get_attr_id("check_objwise_memberwise")

        self.declare_buffer(self.offsets_id, "i8")
        self.declare_init(f"self.{self.offsets_id}.append(0)")

    def register_context(self):
        self.element_reader.register_context()
        super().register_context()
        self.declare_method(
            self.check_objwise_memberwise_id,
            self.check_objwise_memberwise(),
        )
        self.declare_method(self.read_body_id, self.read_body())

    def check_objwise_memberwise(self):
        return f"""
        def {self.check_objwise_memberwise_id}(self, is_memberwise):
            if "{self.objwise_or_memberwise}" == "obj-wise" and is_memberwise:
                raise ValueError(
                    "STLSeqReader({self.name}) expected obj-wise reading but got member-wise"
                )

            if "{self.objwise_or_memberwise}" == "member-wise" and (not is_memberwise):
                raise ValueError(
                    "STLSeqReader({self.name}) expected member-wise reading but got obj-wise"
                )
        """

    def read_body(self):
        return f"""
        def {self.read_body_id}(self, stream, is_memberwise):
            fSize = stream.read_uint32()
            self.{self.offsets_id}.append(self.{self.offsets_id}[len(self.{self.offsets_id}) - 1] + fSize)

            if is_memberwise:
                self.{self.element_reader.read_many_memberwise_id}(stream, fSize)
            else:
                self.{self.element_reader.read_many_id}(stream, fSize)
        """

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            stream.skip_fNBytes()

            fVersion = stream.read_fVersion()
            is_memberwise = bool(fVersion & {kStreamedMemberwise})
            self.{self.check_objwise_memberwise_id}(is_memberwise)

            if is_memberwise:
                stream.skip(2)

            self.{self.read_body_id}(stream, is_memberwise)
        """

    def read_many(self):
        return f"""
        def {self.read_many_id}(self, stream, count):
            if count == 0:
                return 0

            elif count < 0:
                assert {self.with_header}, "STLSeqReader({self.name}).read_many called with negative count expects with_header=True"

                fNBytes = stream.read_fNBytes()
                end_pos = stream.cursor + fNBytes

                fVersion = stream.read_fVersion()
                is_memberwise = bool(fVersion & {kStreamedMemberwise})
                self.{self.check_objwise_memberwise_id}(is_memberwise)

                if is_memberwise:
                    stream.skip(2)

                cur_count = 0
                while stream.cursor < end_pos:
                    self.{self.read_body_id}(stream, is_memberwise)
                    cur_count += 1
                return cur_count

            else:
                is_memberwise = "{self.objwise_or_memberwise}" == "member-wise"
                if {self.with_header}:
                    stream.skip_fNBytes()
                    fVersion = stream.read_fVersion()
                    is_memberwise = bool(fVersion & {kStreamedMemberwise})
                    self.{self.check_objwise_memberwise_id}(is_memberwise)

                if is_memberwise:
                    stream.skip(2)

                for _ in range(count):
                    self.{self.read_body_id}(stream, is_memberwise)
                return count
        """

    def read_until(self):
        return f"""
        def {self.read_until_id}(self, stream, end_pos):
            if stream.cursor == end_pos:
                return 0

            is_memberwise = "{self.objwise_or_memberwise}" == "member-wise"

            if {self.with_header}:
                stream.skip_fNBytes()
                fVersion = stream.read_fVersion()
                is_memberwise = bool(fVersion & {kStreamedMemberwise})
                self.{self.check_objwise_memberwise_id}(is_memberwise)

            if is_memberwise:
                stream.skip(2)

            count = 0
            while stream.cursor < end_pos:
                self.{self.read_body_id}(stream, is_memberwise)
                count += 1
            return count
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_id)
        element_data = self.element_reader.data()
        return offsets, element_data


class STLMapReader(IReader):
    def __init__(
        self,
        name: str,
        context: CompilationContext,
        with_header: bool,
        objwise_or_memberwise: Literal["auto", "obj-wise", "member-wise"],
        key_reader: IReader,
        value_reader: IReader,
    ):
        super().__init__(name, context)

        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.key_reader = key_reader
        self.value_reader = value_reader

        self.offsets_id = self.get_attr_id("offsets")
        self.read_body_id = self.get_attr_id("read_body")
        self.check_objwise_memberwise_id = self.get_attr_id("check_objwise_memberwise")

        self.declare_buffer(self.offsets_id, "i8")
        self.declare_init(f"self.{self.offsets_id}.append(0)")

    def register_context(self):
        self.key_reader.register_context()
        self.value_reader.register_context()
        super().register_context()
        self.declare_method(
            self.check_objwise_memberwise_id,
            self.check_objwise_memberwise(),
        )
        self.declare_method(self.read_body_id, self.read_body())

    def check_objwise_memberwise(self):
        return f"""
        def {self.check_objwise_memberwise_id}(self, is_memberwise):
            if "{self.objwise_or_memberwise}" == "obj-wise" and is_memberwise:
                raise ValueError(
                    "STLMapReader({self.name}) expected obj-wise reading but got member-wise"
                )

            if "{self.objwise_or_memberwise}" == "member-wise" and (not is_memberwise):
                raise ValueError(
                    "STLMapReader({self.name}) expected member-wise reading but got obj-wise"
                )
        """

    def read_body(self):
        return f"""
        def {self.read_body_id}(self, stream, is_memberwise):
            fSize = stream.read_uint32()
            self.{self.offsets_id}.append(self.{self.offsets_id}[len(self.{self.offsets_id}) - 1] + fSize)

            if is_memberwise:
                self.{self.key_reader.read_many_id}(stream, fSize)
                self.{self.value_reader.read_many_id}(stream, fSize)
            else:
                for _ in range(fSize):
                    self.{self.key_reader.read_id}(stream)
                    self.{self.value_reader.read_id}(stream)
        """

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            stream.skip_fNBytes()
            fVersion = stream.read_fVersion()
            stream.skip(6)

            is_memberwise = bool(fVersion & {kStreamedMemberwise})
            self.{self.check_objwise_memberwise_id}(is_memberwise)
            self.{self.read_body_id}(stream, is_memberwise)
        """

    def read_many(self):
        return f"""
        def {self.read_many_id}(self, stream, count):
            if count == 0:
                return 0

            elif count < 0:
                assert {self.with_header}, "STLMapReader({self.name}).read_many called with negative count expecting with_header=True"

                fNBytes = stream.read_fNBytes()
                end_pos = stream.cursor + fNBytes

                fVersion = stream.read_fVersion()
                stream.skip(6)

                is_memberwise = bool(fVersion & {kStreamedMemberwise})
                self.{self.check_objwise_memberwise_id}(is_memberwise)

                cur_count = 0
                while stream.cursor < end_pos:
                    self.{self.read_body_id}(stream, is_memberwise)
                    cur_count += 1
                return cur_count

            else:
                is_memberwise = "{self.objwise_or_memberwise}" == "member-wise"
                if {self.with_header}:
                    stream.skip_fNBytes()
                    fVersion = stream.read_fVersion()
                    stream.skip(6)

                    is_memberwise = bool(fVersion & {kStreamedMemberwise})
                    self.{self.check_objwise_memberwise_id}(is_memberwise)

                for _ in range(count):
                    self.{self.read_body_id}(stream, is_memberwise)
                return count
        """

    def read_until(self):
        return f"""
        def {self.read_until_id}(self, stream, end_pos):
            if stream.cursor == end_pos:
                return 0

            is_memberwise = "{self.objwise_or_memberwise}" == "member-wise"

            if {self.with_header}:
                stream.skip_fNBytes()
                fVersion = stream.read_fVersion()
                stream.skip(6)

                is_memberwise = bool(fVersion & {kStreamedMemberwise})
                self.{self.check_objwise_memberwise_id}(is_memberwise)

            count = 0
            while stream.cursor < end_pos:
                self.{self.read_body_id}(stream, is_memberwise)
                count += 1
            return count
        """

    def read_many_memberwise(self):
        return f"""
        def {self.read_many_memberwise_id}(self, stream, count):
            assert count >= 0, f"Calling {self.name}.read_many_memberwise with negative count: {{count}} is not allowed"

            is_memberwise = True
            self.{self.check_objwise_memberwise_id}(is_memberwise)
            return self.{self.read_many_id}(stream, count)
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_id)
        key_data = self.key_reader.data()
        value_data = self.value_reader.data()
        return offsets, key_data, value_data


class STLStringReader(IReader):
    def __init__(self, name: str, context: CompilationContext, with_header: bool):
        super().__init__(name, context)
        self.with_header = with_header

        self.data_id = self.get_attr_id("data")
        self.offsets_id = self.get_attr_id("offsets")
        self.read_body_id = self.get_attr_id("read_body")

        self.declare_buffer(self.data_id, "u1")
        self.declare_buffer(self.offsets_id, "i8")
        self.declare_init(f"self.{self.offsets_id}.append(0)")

    def register_context(self):
        super().register_context()
        self.declare_method(self.read_body_id, self.read_body())

    def read_body(self):
        return f"""
        def {self.read_body_id}(self, stream):
            fSize = stream.read_uint8()
            if fSize == 255:
                fSize = stream.read_uint32()

            self.{self.offsets_id}.append(self.{self.offsets_id}[len(self.{self.offsets_id}) - 1] + fSize)
            for _ in range(fSize):
                self.{self.data_id}.append(stream.read_uint8())
        """

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            if {self.with_header}:
                stream.skip_fNBytes()
                stream.skip_fVersion()
            self.{self.read_body_id}(stream)
        """

    def read_many(self):
        return f"""
        def {self.read_many_id}(self, stream, count):
            if count == 0:
                return 0

            elif count < 0:
                assert {self.with_header}, "STLStringReader({self.name}).read_many called with negative count expecting with_header=True"

                fNBytes = stream.read_fNBytes()
                end_pos = stream.cursor + fNBytes

                stream.skip_fVersion()

                cur_count = 0
                while stream.cursor < end_pos:
                    self.{self.read_body_id}(stream)
                    cur_count += 1
                return cur_count

            else:
                if {self.with_header}:
                    stream.skip_fNBytes()
                    stream.skip_fVersion()

                for _ in range(count):
                    self.{self.read_body_id}(stream)
                return count
        """

    def read_until(self):
        return f"""
        def {self.read_until_id}(self, stream, end_pos):
            if stream.cursor == end_pos:
                return 0

            if {self.with_header}:
                stream.skip_fNBytes()
                stream.skip_fVersion()

            count = 0
            while stream.cursor < end_pos:
                self.{self.read_body_id}(stream)
                count += 1
            return count
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_id)
        data = self.get_buffer(self.data_id)
        return offsets, data


class TArrayReader(IReader):
    def __init__(
        self,
        name: str,
        context: CompilationContext,
        dtype: Literal["i1", "i2", "i4", "i8", "float", "double"],
    ):
        super().__init__(name, context)

        self.dtype = dtype
        self.stream_method = {
            "i1": "read_int8",
            "i2": "read_int16",
            "i4": "read_int32",
            "i8": "read_int64",
            "float": "read_float",
            "double": "read_double",
        }[self.dtype]

        self.data_id = self.get_attr_id("data")
        self.offsets_id = self.get_attr_id("offsets")

        self.declare_buffer(self.data_id, self.dtype)
        self.declare_buffer(self.offsets_id, "i8")
        self.declare_init(f"self.{self.offsets_id}.append(0)")

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            fSize = stream.read_uint32()
            self.{self.offsets_id}.append(self.{self.offsets_id}[len(self.{self.offsets_id}) - 1] + fSize)

            for _ in range(fSize):
                self.{self.data_id}.append(stream.{self.stream_method}())
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_id)
        data = self.get_buffer(self.data_id)
        return offsets, data


class GroupReader(IReader):
    def __init__(self, name: str, context: CompilationContext, element_readers: list[IReader]):
        super().__init__(name, context)
        self.element_readers = element_readers

    def register_context(self):
        for reader in self.element_readers:
            reader.register_context()
        super().register_context()

    def read(self):
        lines = [f"        def {self.read_id}(self, stream):"]
        if len(self.element_readers) == 0:
            lines.append("            return")
        else:
            for reader in self.element_readers:
                lines.append(f"            self.{reader.read_id}(stream)")
        return "\n".join(lines) + "\n"

    def read_many_memberwise(self):
        lines = [
            f"        def {self.read_many_memberwise_id}(self, stream, count):",
            f'            assert count >= 0, f"Calling {self.name}.read_many_memberwise with negative count: {{count}} is not allowed"',
        ]
        if len(self.element_readers) > 0:
            for reader in self.element_readers:
                lines.append(f"            self.{reader.read_many_id}(stream, count)")
        lines.append("            return count")
        return "\n".join(lines) + "\n"

    def data(self):
        return [reader.data() for reader in self.element_readers]


class AnyClassReader(IReader):
    def __init__(self, name: str, context: CompilationContext, element_readers: list[IReader]):
        super().__init__(name, context)
        self.element_readers = element_readers

    def register_context(self):
        for reader in self.element_readers:
            reader.register_context()
        super().register_context()

    def read(self):
        lines = [
            f"        def {self.read_id}(self, stream):",
            "            fNBytes = stream.read_fNBytes()",
            "            start_pos = stream.cursor",
            "            end_pos = start_pos + fNBytes",
            "",
            "            stream.skip_fVersion()",
            "",
        ]
        for reader in self.element_readers:
            lines.append(f"            self.{reader.read_id}(stream)")

        lines.extend(
            [
                "",
                "            assert stream.cursor == end_pos, (",
                f'                "AnyClassReader({self.name}): Invalid read length! Expect {{fNBytes}} bytes, "',
                '                f"but read {stream.cursor - start_pos} bytes."',
                "            )",
            ]
        )

        return "\n".join(lines) + "\n"

    def read_many_memberwise(self):
        lines = [
            f"        def {self.read_many_memberwise_id}(self, stream, count):",
            f'            assert count >= 0, f"Calling {self.name}.read_many_memberwise with negative count: {{count}} is not allowed"',
        ]
        if len(self.element_readers) > 0:
            for reader in self.element_readers:
                lines.append(f"            self.{reader.read_many_id}(stream, count)")
        lines.append("            return count")
        return "\n".join(lines) + "\n"

    def data(self):
        return [reader.data() for reader in self.element_readers]


class ObjectHeaderReader(IReader):
    def __init__(self, name: str, context: CompilationContext, element_reader: IReader):
        super().__init__(name, context)
        self.element_reader = element_reader

    def register_context(self):
        self.element_reader.register_context()
        super().register_context()

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            fNBytes = stream.read_fNBytes()
            start_pos = stream.cursor
            end_pos = stream.cursor + fNBytes

            fTag = stream.read_int32()
            if fTag == {kNewClassTag}:
                stream.skip_null_terminated_string()

            self.{self.element_reader.read_id}(stream)

            assert stream.cursor == end_pos, (
                "ObjectHeaderReader({self.name}): Invalid read length! Expect "
                + str(fNBytes)
                + " bytes, but read "
                + str(stream.cursor - start_pos)
                + " bytes."
            )
        """

    def data(self):
        return self.element_reader.data()


class CStyleArrayReader(IReader):
    def __init__(
        self,
        name: str,
        context: CompilationContext,
        flat_size: int,
        element_reader: IReader,
    ):
        super().__init__(name, context)
        self.flat_size = flat_size
        self.element_reader = element_reader

        self.offsets_id = self.get_attr_id("offsets")

        if self.flat_size < 0:
            self.declare_buffer(self.offsets_id, "i8")
            self.declare_init(f"self.{self.offsets_id}.append(0)")

    def register_context(self):
        self.element_reader.register_context()
        super().register_context()

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            if {self.flat_size} >= 0:
                self.{self.element_reader.read_many_id}(stream, {self.flat_size})

            else:
                cursor_pos = stream.cursor
                end_pos = -1
                for i in range(stream.offsets.size):
                    if stream.offsets[i] > cursor_pos:
                        end_pos = stream.offsets[i]
                        break

                assert end_pos >= 0, "CStyleArrayReader({self.name}): unable to find end_pos from offsets"

                count = self.{self.element_reader.read_until_id}(stream, end_pos)
                self.{self.offsets_id}.append(self.{self.offsets_id}[len(self.{self.offsets_id}) - 1] + count)
        """

    def read_many(self):
        return f"""
        def {self.read_many_id}(self, stream, count):
            assert {self.flat_size} >= 0, "Calling CStyleArrayReader({self.name}).read_many with negative flat_size is not allowed"
            assert count >= 0, f"Calling CStyleArrayReader({self.name}).read_many with negative count: {{count}} is not allowed"

            for _ in range(count):
                self.{self.element_reader.read_many_id}(stream, {self.flat_size})

            return count
        """

    def read_until(self):
        return f"""
        def {self.read_until_id}(self, stream, end_pos):
            raise NotImplementedError("CStyleArrayReader.read_until is not supported")
        """

    def data(self):
        if self.flat_size >= 0:
            return self.element_reader.data()

        offsets = self.get_buffer(self.offsets_id)
        element_data = self.element_reader.data()
        return offsets, element_data


class EmptyReader(IReader):
    def __init__(self, name: str, context: CompilationContext):
        super().__init__(name, context)

    def read(self):
        return f"""
        def {self.read_id}(self, stream):
            return
        """

    def data(self):
        return None


_compiled_classes = {}


def compile_reader(branch_id: int, reader: IReader):
    if branch_id in _compiled_classes:
        return _compiled_classes[branch_id]

    compiler = Compiler(f"Reader_{branch_id}", reader)
    class_src = compiler.compile()

    local_namespace = {}
    exec(
        compile(
            class_src,
            filename="<dynamic>",
            mode="exec",
        ),
        {"numba": numba},
        local_namespace,
    )
    reader_cls = local_namespace[compiler.cls_name]
    _compiled_classes[branch_id] = reader_cls
    return reader_cls


@nb.njit
def _read_data(stream: Stream, reader):
    for i_evt in range(stream.entries):
        reader.read(stream)
        stream.check_position(i_evt)


def read_data(
    data: np.ndarray,
    offsets: np.ndarray,
    reader: IReader,
    branch_id: int,
    ctx: CompilationContext,
):
    # compile reader if not already compiled
    compiled_reader = compile_reader(branch_id, reader)()
    stream = Stream(data, offsets.astype(np.int64))

    _read_data(stream, compiled_reader)

    for buffer_id, buffer_dtype in ctx.buffer_meta.items():
        transform_func = {
            "bool": list_to_array_uint8,
            "u1": list_to_array_uint8,
            "u2": list_to_array_uint16,
            "u4": list_to_array_uint32,
            "u8": list_to_array_uint64,
            "i1": list_to_array_int8,
            "i2": list_to_array_int16,
            "i4": list_to_array_int32,
            "i8": list_to_array_int64,
            "float": list_to_array_float32,
            "double": list_to_array_float64,
        }[buffer_dtype]
        ctx.buffers[buffer_id] = transform_func(getattr(compiled_reader, buffer_id))

    return reader.data()
