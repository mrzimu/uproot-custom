from __future__ import annotations

import os
import re
import textwrap
from typing import Literal

import awkward as ak
import numpy as np

kNewClassTag = 0xFFFFFFFF
kByteCountMask = 0x40000000
kIsReferenced = 1 << 4
kStreamedMemberwise = 1 << 14

stream_data_token = "__stream_data"
stream_offset_token = "__stream_offset"
stream_ievt_token = "__stream_ievt"
stream_nevt_token = "__stream_nevt"
stream_evt_end_pos_token = "__stream_evt_end_pos"

DTYPE_TO_TYPECODE = {
    "uint8": "B",
    "uint16": "H",
    "uint32": "I",
    "uint64": "Q",
    "int8": "b",
    "int16": "h",
    "int32": "i",
    "int64": "q",
    "float32": "f",
    "float64": "d",
    "bool": "B",
}

_tmp_id = 0

TYPECODE = Literal["B", "H", "I", "Q", "b", "h", "i", "q", "f", "d"]
TYPECODE_SET = {"B", "H", "I", "Q", "b", "h", "i", "q", "f", "d"}

FORTH_OUTPUT_TYPE = Literal[
    "bool",
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "float32",
    "float64",
]

TYPECODE_TO_FORTH_OUTPUT_TYPE: dict[TYPECODE, FORTH_OUTPUT_TYPE] = {
    "B": "uint8",
    "H": "uint16",
    "I": "uint32",
    "Q": "uint64",
    "b": "int8",
    "h": "int16",
    "i": "int32",
    "q": "int64",
    "f": "float32",
    "d": "float64",
}

comment_pattern1 = re.compile(r"\\.*")
comment_pattern2 = re.compile(r"\( .* \)")
userword_pattern = re.compile(r": ([\w]+) ([^;]+) ;")


def _format_forth_codes(codes: str) -> str:
    # remove comment
    lines = codes.split("\n")
    formatted_lines = []
    for line in lines:
        line = comment_pattern1.sub("", line)
        line = comment_pattern2.sub("", line)
        formatted_lines.append(line.strip())

    # concat lines with single space
    # codes = " ".join(formatted_lines)
    # codes = codes.replace(" :", "\n:").replace(" ;", "\n;\n\n")
    codes = "\n".join(formatted_lines)
    codes = re.sub(r"\n\n\n+", "\n\n", codes)
    return codes


def to_typecode(dtype_or_typecode: str) -> TYPECODE:
    if dtype_or_typecode in DTYPE_TO_TYPECODE:
        return DTYPE_TO_TYPECODE[dtype_or_typecode]

    if dtype_or_typecode in TYPECODE_SET:
        return dtype_or_typecode

    raise ValueError(f"Unsupported dtype/typecode: {dtype_or_typecode}")


def read_data(data: bytes, offsets: np.ndarray, reader: IReader):
    read_single_evt_code = reader.compile()

    n_evt = len(offsets) - 1
    offsets_be = np.asarray(offsets, dtype=">u4")

    # Finish event-loop
    codes = f"""
    input {stream_data_token}
    input {stream_offset_token}

    {reader._buffer_holder.declare_output()}

    \\ current event index
    variable {stream_ievt_token}

    \\ current event end position in stream
    variable {stream_evt_end_pos_token}

    \\ consume first offset (usually 0)
    {stream_offset_token} !I-> stack drop

    {read_single_evt_code}

    {n_evt} 0 do
        i {stream_ievt_token} !

        {debug_print('cr ." ====================================>" cr')}
        {debug_print(f'." Starting event " {stream_ievt_token} @ . cr')}
        {debug_print_input(stream_data_token)}
        {debug_print('cr')}

        \\ consume next offset as current event end position
        {stream_offset_token} !I-> stack
        {stream_evt_end_pos_token} !

        {reader.read_token}
    loop
    """

    codes = _format_forth_codes(codes)

    vm = ak.forth.ForthMachine64(codes)
    vm.run(
        {
            stream_data_token: data.copy(),
            stream_offset_token: offsets_be.copy(),
        }
    )

    outputs: dict[str, np.ndarray] = vm.outputs

    reader._buffer_holder.buffers = outputs
    return reader.data()


def read_number(typecode: TYPECODE, target: str = None):
    if target is not None:
        return f"{stream_data_token} !{typecode}-> {target}"
    else:
        return f"{stream_data_token} !{typecode}-> stack"


def read_many_number(typecode: TYPECODE, target: str = None):
    if target is not None:
        return f"{stream_data_token} #!{typecode}-> {target}"
    else:
        return f"{stream_data_token} #!{typecode}-> stack"


def read_bool(target: str = None):
    return read_number("B", target)


def read_int8(target: str = None):
    return read_number("b", target)


def read_uint8(target: str = None):
    return read_number("B", target)


def read_int16(target: str = None):
    return read_number("h", target)


def read_uint16(target: str = None):
    return read_number("H", target)


def read_int32(target: str = None):
    return read_number("i", target)


def read_uint32(target: str = None):
    return read_number("I", target)


def read_int64(target: str = None):
    return read_number("q", target)


def read_uint64(target: str = None):
    return read_number("Q", target)


def read_float(target: str = None):
    return read_number("f", target)


def read_double(target: str = None):
    return read_number("d", target)


def read_fNBytes():
    global _tmp_id

    res = f"""
    \\ ===== Begin read_FNBytes =====
    {read_uint32()}
    dup {kByteCountMask} and 0= \\ if not (fNBytes & kByteCountMask), halt
    if
        ." Invalid fNBytes " {_tmp_id} . ." value=" .
        halt
    then

    {kByteCountMask} invert and
    \\ ===== End read_FNBytes =====
    """

    _tmp_id += 1

    return textwrap.dedent(res)


def read_fVersion():
    return read_uint16()


def skip(bytes: int):
    return f"{bytes} {stream_data_token} skip"


def skip_fNBytes():
    global _tmp_id

    res = f"""
    {read_uint32()}

    dup {kByteCountMask} and 0= \\ if not (fNBytes & kByteCountMask), halt
    if
        ." Invalid fNBytes " {_tmp_id} . ." value=" .
        halt
    then

    drop
    """

    _tmp_id += 1
    return res


def skip_fVersion():
    return skip(2)


def add_and_append(target: str):
    return f"{target} +<- stack"


def _format_method_code(code: str, method_token: str):
    return textwrap.dedent(f"""
    \\ ======================== Begin {method_token} ========================
    {code}
    \\ ======================== End {method_token} ========================
    """)


def debug_print(code: str):
    if "UPROOT_DEBUG" not in os.environ:
        return ""
    return code


def debug_print_input(token: str, nbytes: int = 40):
    if "UPROOT_DEBUG" not in os.environ:
        return ""

    return f"""
    \\ calculate max number of items to print based on nbytes and item size
    {token} len \\ stack: [len]
    {token} pos \\ stack: [len, pos]
    -           \\ stack: [remaining_nytes]
    {nbytes} min \\ stack: [nbytes_to_print]

    \\ Debug print input {token}
    dup 0 do {token} !B-> stack . ." " loop cr \\ stack: [nbytes_to_print]

    \\ go back
    negate {token} skip

    \\ end debug print
    """


class BufferHolder:
    def __init__(self):
        self.buffers: dict[str, np.ndarray] = {}
        self.buffer_meta: dict[str, TYPECODE] = {}

    @staticmethod
    def to_forth_output_type(typecode: TYPECODE) -> FORTH_OUTPUT_TYPE:
        return TYPECODE_TO_FORTH_OUTPUT_TYPE[typecode]

    def declare_output(self) -> str:
        return "\n".join(
            f"output {token} {self.to_forth_output_type(typecode)}"
            for token, typecode in self.buffer_meta.items()
        )


class IReader:
    def __init__(self, name: str, buffer_holder: BufferHolder):
        self.name = name

        cls_name = self.__class__.__name__
        obj_hash = str(hash(self))
        for i in range(10):
            obj_hash = obj_hash.replace(str(i), chr(ord("a") + i))

        self._id = f"{cls_name}_{self.name}_{obj_hash}"

        self.read_token = f"{self._id}_read"
        self.read_many_token = f"{self._id}_read_many"
        self.read_until_token = f"{self._id}_read_until"
        self.read_many_memberwise_token = f"{self._id}_read_many_memberwise"

        self._buffer_holder = buffer_holder

    @property
    def _buffer_meta(self):
        return self._buffer_holder.buffer_meta

    @property
    def _buffers(self):
        return self._buffer_holder.buffers

    def register_buffer(self, buffer_name: str, dtype_or_typecode: str) -> str:
        buffer_token = f"{self._id}_buffer_{buffer_name}"
        assert (
            buffer_token not in self._buffer_meta
        ), f"Buffer {buffer_name} already registered for reader {self.name}"

        typecode = to_typecode(dtype_or_typecode)
        self._buffer_meta[buffer_token] = typecode
        return buffer_token

    def get_buffer(self, buffer_token: str) -> np.ndarray:
        return self._buffers[buffer_token]

    def compile(self) -> str:
        res = "\n"

        # declare functions
        read_codes = _format_method_code(
            self.read(),
            self.read_token,
        )
        read_many_codes = _format_method_code(
            self.read_many(),
            self.read_many_token,
        )
        read_until_codes = _format_method_code(
            self.read_until(),
            self.read_until_token,
        )
        read_many_memberwise_codes = _format_method_code(
            self.read_many_memberwise(),
            self.read_many_memberwise_token,
        )

        res_template = """
        : {read_token} ( -- )
        {read_codes}
        ;

        : {read_many_token} ( count -- )
        {read_many_codes}
        ;

        : {read_until_token} ( end_pos -- )
        {read_until_codes}
        ;

        : {read_many_memberwise_token} ( count -- )
        {read_many_memberwise_codes}
        ;
        """
        res_template = textwrap.dedent(res_template)
        res = res_template.format(
            read_token=self.read_token,
            read_codes=read_codes,
            read_many_token=self.read_many_token,
            read_many_codes=read_many_codes,
            read_until_token=self.read_until_token,
            read_until_codes=read_until_codes,
            read_many_memberwise_token=self.read_many_memberwise_token,
            read_many_memberwise_codes=read_many_memberwise_codes,
        )

        return res

    def read(self) -> str:
        raise NotImplementedError

    def read_many(self) -> str:
        """
        Take <num-items> from stack, read that many items.
        """

        return f"dup 0 do {self.read_token} loop"

    def read_until(self) -> str:
        """
        Take <end-pos> from stack, read until that position is reached.
        """

        return f"""
        0 swap \\ add counter for number of items read
        begin
            \\ Check if we've reached the end position
            dup {stream_data_token} pos = invert
        while
            {self.read_token}
            swap 1+ swap \\ increment counter
        repeat

        \\ clear the end position from stack
        drop
        """

    def read_many_memberwise(self) -> str:
        return f"""
        ." Calling {self.name}.read_many_memberwise is not supported" .
        halt
        """

    def data(self):
        raise NotImplementedError

    def iter_subreaders(self) -> list[IReader]:
        return []

    def test_compile(self):
        for reader in self.iter_subreaders():
            reader.test_compile()

        codes = f"""
        input {stream_data_token}
        input {stream_offset_token}

        {self._buffer_holder.declare_output()}

        variable {stream_ievt_token}
        variable {stream_evt_end_pos_token}

        {self.compile()}
        """

        ak.forth.ForthMachine64(codes)


class PrimitiveReader(IReader):
    def __init__(
        self,
        name: str,
        dtype: Literal[
            "bool",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
            "int8",
            "int16",
            "int32",
            "int64",
            "float32",
            "float64",
        ],
        buffer_holder: BufferHolder,
    ):
        super().__init__(name, buffer_holder)

        self.dtype = dtype
        self.typecode = to_typecode(dtype)
        self.data_token = self.register_buffer(name, dtype)

    def read(self) -> str:
        return f"{stream_data_token} !{self.typecode}-> {self.data_token}"

    def read_many(self):
        return f"dup {stream_data_token} #!{self.typecode}-> {self.data_token}"

    def read_until(self):
        element_size = np.dtype(self.dtype).itemsize

        return f"""
        \\ Calculate number of items to read based on end position
        {stream_data_token} pos - {element_size} /

        \\ Call read_many to read all items until end position
        {self.read_many_token}
        """

    def data(self):
        return self.get_buffer(self.data_token)


class TObjectReader(IReader):
    def __init__(self, name: str, keep_data: bool, buffer_holder: BufferHolder):
        super().__init__(name, buffer_holder)

        self.keep_data = keep_data

        if self.keep_data:
            self.unique_id_token = self.register_buffer("unique_id", "i")
            self.bits_token = self.register_buffer("bits", "I")
            self.pidf_token = self.register_buffer("pidf", "H")

    def read(self) -> str:
        if self.keep_data:
            read_pidf_codes = f"{stream_data_token} !H-> {self.pidf_token}"
            save_data_codes = f"""
            \\ stack: [fUniqueID, fBits]
            {self.bits_token} <- stack
            {self.pidf_token} <- stack
        """
        else:
            read_pidf_codes = skip(2)
            save_data_codes = "drop drop"

        return f"""
        {skip_fVersion()}

        \\ Read fUniqueID and fBits
        {read_int32()} {read_uint32()} \\ stack: [fUniqueID, fBits]

        \\ if (fBits & kIsReferenced != 0), read pidf
        dup {kIsReferenced} and
        if
            {read_pidf_codes}
        then
        \\ stack: [fUniqueID, fBits]

        {save_data_codes}
        """

    def data(self):
        if not self.keep_data:
            return None

        unique_id = self.get_buffer(self.unique_id_token)
        bits = self.get_buffer(self.bits_token)
        pidf = self.get_buffer(self.pidf_token)

        # No multiple pidf values for now, we create a dummy offsets here
        pidf_offsets = np.arange(len(pidf) + 1, dtype=np.int64)

        return unique_id, bits, pidf, pidf_offsets


class TStringReader(IReader):
    def __init__(self, name: str, with_header: bool, buffer_holder: BufferHolder):
        super().__init__(name, buffer_holder)
        self.with_header = with_header

        self.data_token = self.register_buffer("data", "B")
        self.offsets_token = self.register_buffer("offsets", "q")

    def compile(self):
        # Add an 0 offset at the beginning
        return super().compile() + f"0 {self.offsets_token} <- stack"

    def read(self):
        return f"""
        {read_uint8()} \\ stack: [fSize]

        dup 255 =           \\ stack: [fSize, is_large]
        if                  \\ stack: [fSize]
            drop            \\ stack: []
            {read_uint32()} \\ stack: [fSize]
        then

        dup {read_many_number('B', self.data_token)} \\ stack: [fSize]

        \\ Update offsets
        {self.offsets_token} +<- stack
        """

    def read_many(self):
        res = """
        \\ stack: [num_items]

        \\ if count < 0, raise error
        dup 0 >= invert
        if
            ." Calling read_many with non-positive count:" . cr
            halt
        then

        \\ stack: [num_items]

        \\ If count == 0, do nothing
        dup 0=
        if          \\ stack: [num_items]
            drop    \\ stack: []
            0       \\ stack: [0]
            exit
        then
        """

        if self.with_header:
            res += f"""
            {skip_fNBytes()}
            {skip_fVersion()}
            """

        res += f"""
        \\ stack: [num_items]
        dup 0 do {self.read_token} loop

        \\ final stack: [num_items]
        """

        return res

    def read_until(self):
        res = f"""
        \\ stack: [end_pos]
        dup {stream_data_token} pos =
        if
            drop
            0
            exit
        then
        """

        if self.with_header:
            res += f"""
            {skip_fNBytes()}
            {skip_fVersion()}
            """

        res += f"""
        \\ stack: [end_pos]
        0 swap \\ stack: [0, end_pos] - counter for number of items read
        begin
            dup {stream_data_token} pos = invert
        while
            {self.read_token}
            swap 1+ swap \\ increment counter
        repeat
        \\ clear the end position from stack
        drop
        """

        return res

    def data(self):
        data = self.get_buffer(self.data_token)
        offsets = self.get_buffer(self.offsets_token)
        return offsets, data


class STLSeqReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
        objwise_or_memberwise: Literal["auto", "obj-wise", "member-wise"],
        element_reader: IReader,
        buffer_holder: BufferHolder,
    ):
        super().__init__(name, buffer_holder)

        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.element_reader = element_reader

        self.objwise_or_memberwise_flag = {
            "obj-wise": 0,
            "member-wise": 1,
            "auto": 2,
        }[self.objwise_or_memberwise]
        self.with_header_flag = 1 if self.with_header else 0

        self.offsets_token = self.register_buffer("offsets", "q")

    def compile(self):
        return self.element_reader.compile() + f"""
        \\ initialize offsets with 0
        0 {self.offsets_token} <- stack
        """ + super().compile()

    def check_objwise_memberwise(self):
        # stack: [is_memberwise] --> []
        if self.objwise_or_memberwise == "auto":
            res = "drop"

        else:
            another = "member-wise" if self.objwise_or_memberwise == "obj-wise" else "obj-wise"

            res = f"""\\ stack: [is_memberwise]
            {self.objwise_or_memberwise_flag} = invert
            if
                ." STLSeqReader({self.name}) expected {self.objwise_or_memberwise} but got {another}" .
                halt
            then
            """

        return _format_method_code(
            textwrap.dedent(res),
            f"{self.name}.check_objwise_memberwise",
        )

    def read_body(self):
        """
        stack: [is_memberwise] -> []
        """

        dbg_code = f'." STLSeqReader({self.name}): reading body, (is_memberwise, fSize)="  over . dup . cr'

        res = f"""
        \\ stack: [is_memberwise]
        {read_uint32()} \\ stack: [is_memberwise, fSize]

        \\ Update offsets
        dup {add_and_append(self.offsets_token)} \\ stack: [is_memberwise, fSize]

        {debug_print(dbg_code)}
        {debug_print('." - stack: " .s cr ." - data: "')}
        {debug_print_input(stream_data_token)}

        swap \\ stack: [fSize, is_memberwise]
        if \\ stack: [fSize]
            {self.element_reader.read_many_memberwise_token}
        else
            {self.element_reader.read_many_token}
        then
        drop

        {debug_print(f'." Finished reading body for {self.name}" cr ." - stack: " .s cr')}

        \\ final stack: []
        """

        return _format_method_code(
            textwrap.dedent(res),
            f"{self.name}.read_body",
        )

    def read(self):
        return f"""
        {skip_fNBytes()}

        {read_fVersion()} {kStreamedMemberwise} and \\ stack: [is_memberwise]
        dup {self.check_objwise_memberwise()} \\ stack: [is_memberwise]

        dup
        if
            {skip(2)}
        then

        {self.read_body()}
        """

    def read_many(self):
        with_header_block = ""
        if self.with_header:
            with_header_block = f"""\\ stack: [is_memberwise_old]
                {skip_fNBytes()}

                drop {read_fVersion()} {kStreamedMemberwise} and \\ stack: [is_memberwise_new]
                dup {self.check_objwise_memberwise()} \\ stack: [is_memberwise_new]
            """

        negative_count_block = ""
        if self.with_header:
            negative_count_block = f"""
            {read_fNBytes()}        \\ stack: [count(-1), fNBytes]
            {stream_data_token} pos +    \\ stack: [count(-1), end_pos]

            {read_fVersion()}           \\ stack: [count(-1), end_pos, version]
            {kStreamedMemberwise} and   \\ stack: [count(-1), end_pos, is_memberwise]

            dup {self.check_objwise_memberwise()} \\ stack: [count(-1), end_pos, is_memberwise]

            dup if
                {skip(2)}
            then

            0 \\ stack: [count(-1), end_pos, is_memberwise, 0] - counter for number of items read
            begin
                rot \\ stack: [count(-1), is_memberwise, counter, end_pos]
                dup {stream_data_token} pos = invert \\ stack: [count(-1), is_memberwise, counter, end_pos, not_at_end]
            while                   \\ stack: [count(-1), is_memberwise, counter, end_pos]
                rot dup             \\ stack: [count(-1), counter, end_pos, is_memberwise, is_memberwise]
                {self.read_body()}  \\ stack: [count(-1), counter, end_pos, is_memberwise]
                rot 1+              \\ stack: [count(-1), end_pos, is_memberwise, counter+1]
            repeat
            \\ stack: [count(-1), end_pos, is_memberwise, counter]

            rot rot drop drop   \\ stack: [count(-1), counter]
            swap drop           \\ stack: [counter]
            """
        else:
            negative_count_block = f"""
            ." STLSeqReader({self.name}).read_many called with negative count expects with_header=True" .
            halt
            """

        return f"""\\ stack: [count]
        {debug_print(f'." In STLSeqReader({self.name}) read_many:" cr ." - data: " cr')}
        {debug_print_input(stream_data_token)}
        {debug_print('." - stack: " .s cr')}

        dup 0=
        if
            exit
        then

        dup 0 <
        if
            {negative_count_block}
        else
            {1 if self.objwise_or_memberwise_flag==1 else 0} \\ stack: [count, is_memberwise], 1 is member-wise flag

            {debug_print(f'." STLSeqReader({self.name}) read_many[1]:" cr ." - data:"')}
            {debug_print_input(stream_data_token)}
            {debug_print('." - stack: " .s cr')}

            {with_header_block} \\ stack: [count, is_memberwise]

            {debug_print(f'." STLSeqReader({self.name}) read_many[2]:" cr ." - data:"')}
            {debug_print_input(stream_data_token)}
            {debug_print('." - stack: " .s cr')}

            dup if {skip(2)} then \\ stack: [count, is_memberwise]

            over \\ stack: [count, is_memberwise, count]
            0 do \\ stack: [count, is_memberwise]
                {debug_print(f'." STLSeqReader({self.name}) before read_body:" cr ." - data:"')}
                {debug_print_input(stream_data_token)}
                {debug_print('." - stack: " .s cr')}
                dup {self.read_body()}
            loop \\ stack: [count, is_memberwise]

            drop \\ stack: [count]
        then
        """

    def read_until(self):
        with_header_block = ""
        if self.with_header:
            with_header_block = f"""
            {skip_fNBytes()} \\ stack: [is_memberwise_old]

            drop {read_fVersion()} {kStreamedMemberwise} and \\ stack: [is_memberwise_new]
            dup {self.check_objwise_memberwise()} \\ stack: [is_memberwise_new]
            """

        return f"""\\ stack: [end_pos]
        dup {stream_data_token} pos =
        if
            drop
            0
            exit
        then

        {self.objwise_or_memberwise_flag} \\ stack: [end_pos, is_memberwise]

        {with_header_block} \\ stack: [end_pos, is_memberwise]

        dup if {skip(2)} then \\ stack: [end_pos, is_memberwise]

        0 rot \\ stack: [is_memberwise, count, end_pos]
        begin
            dup {stream_data_token} pos > \\ stack: [is_memberwise, count, end_pos, not_at_end]
        while   \\ stack: [is_memberwise, count, end_pos]
            rot \\ stack: [count, end_pos, is_memberwise]
            dup \\ stack: [count, end_pos, is_memberwise, is_memberwise]
            {self.read_body()} \\ stack: [count, end_pos, is_memberwise]
            rot \\ stack: [end_pos, is_memberwise, count]
            1+
            rot \\ stack: [is_memberwise, count+1, end_pos]
        repeat

        drop swap drop \\ stack: [count]

        {debug_print(f'." Finished read_until for {self.name}" cr ." - data: "')}
        {debug_print_input(stream_data_token)}
        {debug_print('." - stack: " .s cr')}
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_token)
        element_data = self.element_reader.data()
        return offsets, element_data

    def iter_subreaders(self):
        return [self.element_reader]


class STLMapReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
        objwise_or_memberwise: Literal["auto", "obj-wise", "member-wise"],
        key_reader: IReader,
        value_reader: IReader,
        buffer_holder: BufferHolder,
    ):
        super().__init__(name, buffer_holder)

        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.key_reader = key_reader
        self.value_reader = value_reader

        self.objwise_or_memberwise_flag = {
            "obj-wise": 0,
            "member-wise": 1,
            "auto": 2,
        }[self.objwise_or_memberwise]
        self.with_header_flag = 1 if self.with_header else 0

        self.offsets_token = self.register_buffer("offsets", "q")

    def compile(self):
        return self.key_reader.compile() + self.value_reader.compile() + f"""
        0 {self.offsets_token} <- stack
        """ + super().compile()

    def check_objwise_memberwise(self):
        """
        stack: [is_memberwise] -> []
        """
        if self.objwise_or_memberwise == "auto":
            return "drop"

        another = "member-wise" if self.objwise_or_memberwise == "obj-wise" else "obj-wise"
        res = f"""
        \\ stack: [is_memberwise]
        {self.objwise_or_memberwise_flag} = invert
        if
            ." STLMapReader({self.name}) expected {self.objwise_or_memberwise} but got {another}" .
            halt
        then
        """

        return _format_method_code(
            textwrap.dedent(res),
            f"{self.name}.check_objwise_memberwise",
        )

    def read_body(self):
        """
        stack: [is_memberwise] -> []
        """

        res = f"""
        {debug_print(f'." STLMapReader({self.name}): reading body[1], stack: " .s cr')}

        \\ stack: [is_memberwise]
        {read_uint32()} \\ stack: [is_memberwise, fSize]

        dup {add_and_append(self.offsets_token)} \\ stack: [is_memberwise, fSize]

        \\ debug print
        {debug_print(f'." STLMapReader({self.name}): reading body[2], (is_memberwise, fSize)=" over . dup . cr ." - data: "')}
        {debug_print_input(stream_data_token)}
        {debug_print('." - stack: " .s cr')}

        swap \\ stack: [fSize, is_memberwise]
        if \\ stack: [fSize]
            {self.key_reader.read_many_token} \\ stack: [fSize]
            {self.value_reader.read_many_token} \\ stack: [fSize]
            drop
        else    \\ stack: [fSize]
            0 do
                {self.key_reader.read_token}
                {self.value_reader.read_token}
            loop
        then
        """

        return _format_method_code(
            textwrap.dedent(res),
            f"{self.name}.read_body",
        )

    def read(self):
        return f"""
        {skip_fNBytes()}
        {read_fVersion()} \\ stack: [fVersion]
        {skip(6)}

        {kStreamedMemberwise} and \\ stack: [is_memberwise]
        dup {self.check_objwise_memberwise()}

        {self.read_body()}
        """

    def read_many(self):
        with_header_block = ""
        if self.with_header:
            with_header_block = f"""
            {skip_fNBytes()}
            drop {read_fVersion()}
            {skip(6)}

            {kStreamedMemberwise} and
            dup {self.check_objwise_memberwise()}
            """

        negative_count_block = ""
        if self.with_header:
            negative_count_block = f"""
            {read_fNBytes()}        \\ stack: [count(-1), fNBytes]
            {stream_data_token} pos +    \\ stack: [count(-1), end_pos]

            {read_fVersion()}       \\ stack: [count(-1), end_pos, version]
            {skip(6)}
            {kStreamedMemberwise} and \\ stack: [count(-1), end_pos, is_memberwise]

            dup {self.check_objwise_memberwise()} \\ stack: [count(-1), end_pos, is_memberwise]

            0 \\ stack: [count(-1), end_pos, is_memberwise, count]
            begin
                rot \\ stack: [count(-1), is_memberwise, count, end_pos]
                dup {stream_data_token} pos >
            while
                rot \\ stack: [count(-1), count, end_pos, is_memberwise]
                dup \\ stack: [count(-1), count, end_pos, is_memberwise, is_memberwise]
                {self.read_body()}  \\ stack: [count(-1), count, end_pos, is_memberwise]
                rot \\ stack: [count(-1), end_pos, is_memberwise, count]
                1+  \\ stack: [count(-1), end_pos, is_memberwise, count+1]
            repeat

            \\ stack: [count(-1), end_pos, is_memberwise, count]

            rot rot drop drop
            swap drop
            """
        else:
            negative_count_block = f"""
            ." STLMapReader({self.name}).read_many called with negative count expecting with_header=True" .
            halt
            """

        return f"""\\ stack: [count]

        {debug_print(f'." In STLMapReader({self.name}) read_many:" cr ." - data: "')}
        {debug_print_input(stream_data_token)}
        {debug_print('." - stack: " .s cr')}

        dup 0=
        if
            drop
            0
            exit
        then

        dup 0 <
        if
            {negative_count_block}
        else
            {self.objwise_or_memberwise_flag} 1 = \\ stack: [count, is_memberwise]

            {with_header_block} \\ stack: [count, is_memberwise]

            over 0 do
                {debug_print(f'." STLMapReader({self.name}) read_many begin statement, stack: " .s cr')}
                dup {self.read_body()}
            loop

            drop
        then
        """

    def read_until(self):
        with_header_block = f"{self.with_header_flag}"
        if self.with_header:
            with_header_block = f"""
            \\ stack: [end_pos, is_memberwise_old]
            drop

            {skip_fNBytes()}
            {read_fVersion()}
            {skip(6)}
            {kStreamedMemberwise} and
            \\ stack: [end_pos, is_memberwise_new]

            dup {self.check_objwise_memberwise()}
            \\ stack: [end_pos, is_memberwise_new]
            """

        return f"""\\ stack: [end_pos]
        dup {stream_data_token} pos =
        if
            drop
            0
            exit
        then

        {self.objwise_or_memberwise_flag} 1 = \\ stack: [end_pos, is_memberwise]

        {with_header_block}

        swap 0 swap \\ stack: [is_memberwise, count, end_pos]
        begin
            dup {stream_data_token} pos > \\ stack: [is_memberwise, count, end_pos, (end_pos>pos)]
            {debug_print('." begin statement: " .s cr')}
        while   \\ stack: [is_memberwise, count, end_pos]
            rot \\ stack: [count, end_pos, is_memberwise]
            dup \\ stack: [count, end_pos, is_memberwise, is_memberwise]
            {debug_print('." before read_body: " .s cr')}
            {self.read_body()} \\ stack: [count, end_pos, is_memberwise]
            rot 1+ \\ stack: [end_pos, is_memberwise, count+1]
            rot \\ stack: [is_memberwise, count+1, end_pos]
        repeat

        drop swap drop
        """

    def read_many_memberwise(self):
        return f"""\\ stack: [count]
        dup 0 <
        if
            ." Calling {self.name}.read_many_memberwise with negative count is not allowed" .
            halt
        then

        1 dup {self.check_objwise_memberwise()} drop
        {self.read_many_token}
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_token)
        key_data = self.key_reader.data()
        value_data = self.value_reader.data()
        return offsets, key_data, value_data

    def iter_subreaders(self):
        return [self.key_reader, self.value_reader]


class STLStringReader(IReader):
    def __init__(self, name: str, with_header: bool, buffer_holder: BufferHolder):
        super().__init__(name, buffer_holder)
        self.with_header = with_header

        self.data_token = self.register_buffer("data", "B")
        self.offsets_token = self.register_buffer("offsets", "q")

    def compile(self):
        return super().compile() + f"0 {self.offsets_token} <- stack"

    def read_body(self):
        """
        stack: [] -> []
        """
        res = f"""
        {read_uint8()} \\ stack: [fSize]

        dup 255 =
        if
            drop
            {read_uint32()}
        then

        \\ stack: [fSize]
        dup {self.offsets_token} +<- stack
        {read_many_number('B', self.data_token)}
        """

        res = _format_method_code(
            textwrap.dedent(res),
            f"{self.name}.read_body",
        )
        return res

    def read(self):
        with_header_block = ""
        if self.with_header:
            with_header_block = f"""
            {skip_fNBytes()}
            {skip_fVersion()}
            """

        return f"""
        {with_header_block}
        {self.read_body()}
        """

    def read_many(self):
        """
        stack: [count] -> [count]
        """
        with_header_block = ""
        if self.with_header:
            with_header_block = f"""
            {skip_fNBytes()}
            {skip_fVersion()}
            """

        negative_count_block = ""
        if self.with_header:
            negative_count_block = f"""
            {read_fNBytes()}        \\ stack: [count(-1), fNBytes]
            {stream_data_token} pos +    \\ stack: [count(-1), end_pos]
            {skip_fVersion()}

            0 swap \\ stack: [count(-1), 0, end_pos]
            begin
                dup {stream_data_token} pos > \\ stack: [count(-1), counter, end_pos, not_at_end]
            while                   \\ stack: [count(-1), counter, end_pos]
                {self.read_body()}  \\ stack: [count(-1), counter, end_pos]
                swap 1+ swap
            repeat

            \\ stack: [count(-1), counter, end_pos]
            drop swap drop
            """
        else:
            negative_count_block = f"""
            ." STLStringReader({self.name}).read_many called with negative count expecting with_header=True" .
            halt
            """

        return f"""
        \\ stack: [count]
        dup 0=
        if
            exit
        then

        dup 0 <
        if
            {negative_count_block}
        else
            {with_header_block}

            dup 0 do
                {self.read_body()}
            loop
        then
        """

    def read_until(self):
        with_header_block = ""
        if self.with_header:
            with_header_block = f"""
            {skip_fNBytes()}
            {skip_fVersion()}
            """

        return f"""\\ stack: [end_pos]
        dup {stream_data_token} pos =
        if
            drop
            0
            exit
        then

        {debug_print('." STLString begin:"')}
        {debug_print_input(stream_data_token)}

        {with_header_block}

        \\ stack: [end_pos]
        0 swap \\ stack: [count, end_pos]
        begin
            dup {stream_data_token} pos > \\ end-pos >= pos
        while \\ stack: [count, end_pos]
            {debug_print(f'." - element " over . ." pos: " {stream_data_token} pos . dup .')}
            {debug_print_input(stream_data_token)}
            {self.read_body()}
            swap 1+ swap
        repeat

        \\ stack: [count, end_pos]
        drop
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_token)
        data = self.get_buffer(self.data_token)
        return offsets, data


class TArrayReader(IReader):
    def __init__(
        self,
        name: str,
        dtype: Literal["int8", "int16", "int32", "int64", "float32", "float64"],
        buffer_holder: BufferHolder,
    ):
        super().__init__(name, buffer_holder)

        self.dtype = dtype
        self.typecode = to_typecode(dtype)

        self.data_token = self.register_buffer("data", dtype)
        self.offsets_token = self.register_buffer("offsets", "q")

    def compile(self):
        return super().compile() + f"0 {self.offsets_token} <- stack"

    def read(self):
        return f"""
        {read_uint32()} \\ stack: [fSize]

        dup {add_and_append(self.offsets_token)} \\ stack: [fSize]
        {read_many_number(self.typecode, self.data_token)}
        """

    def data(self):
        offsets = self.get_buffer(self.offsets_token)
        data = self.get_buffer(self.data_token)
        return offsets, data


class GroupReader(IReader):
    def __init__(self, name: str, element_readers: list[IReader], buffer_holder: BufferHolder):
        super().__init__(name, buffer_holder)
        self.element_readers = element_readers

    def compile(self):
        return "".join(reader.compile() for reader in self.element_readers) + super().compile()

    def read(self):
        return "\n".join(reader.read_token for reader in self.element_readers)

    def read_many_memberwise(self):
        chunks = [f"""\\ stack: [count]
            dup 0 <
            if
                ." Calling {self.name}.read_many_memberwise with negative count is not allowed" .
                halt
            then
            """]
        for reader in self.element_readers:
            chunks.append(f"dup {reader.read_many_token}")
        chunks.append("drop")
        chunks.append("\\ stack: [count]")
        return "\n".join(chunks)

    def data(self):
        return [reader.data() for reader in self.element_readers]

    def iter_subreaders(self):
        return self.element_readers


class AnyClassReader(IReader):
    def __init__(self, name: str, element_readers: list[IReader], buffer_holder: BufferHolder):
        super().__init__(name, buffer_holder)
        self.element_readers = element_readers

    def compile(self):
        return "".join(reader.compile() for reader in self.element_readers) + super().compile()

    def read(self):
        chunks = [f"""
            {read_fNBytes()}
            {stream_data_token} pos + \\ stack: [end_pos]
            {skip_fVersion()}
            """]

        for r in self.element_readers:
            chunks.append(
                debug_print(f'." AnyClassReader({self.name}): reading element {r.name}:" cr')
            )
            chunks.append(debug_print('." before: " cr ." - stream: "'))
            chunks.append(debug_print_input(stream_data_token))
            chunks.append(debug_print('." - stack: " .s cr'))
            chunks.append(r.read_token)
            chunks.append(debug_print('." after: " cr ." - stream: "'))
            chunks.append(debug_print_input(stream_data_token))
            chunks.append(debug_print('." - stack: " .s cr'))

        chunks.append(f"""
            dup {stream_data_token} pos = invert
            if
                ." AnyClassReader({self.name}): Invalid read length: " {stream_data_token} pos . {stream_evt_end_pos_token} @ . cr
                halt
            then
            drop
            """)
        return "\n".join(chunks)

    def read_many_memberwise(self):
        chunks = [f"""\\ stack: [count]
            dup 0 <
            if
                ." Calling {self.name}.read_many_memberwise with negative count is not allowed" .
                halt
            then
            """]
        for reader in self.element_readers:
            chunks.append(f"{reader.read_many_token}")
        chunks.append("\\ stack: [count]")
        res = "\n".join(chunks)

        res += f"""
        {debug_print(f'." AnyClassReader({self.name}): finished read_many_memberwise" cr ." - stack: " .s cr')}
        """

        return res

    def data(self):
        return [reader.data() for reader in self.element_readers]

    def iter_subreaders(self):
        return self.element_readers


class ObjectHeaderReader(IReader):
    def __init__(self, name: str, element_reader: IReader, buffer_holder: BufferHolder):
        super().__init__(name, buffer_holder)
        self.element_reader = element_reader

    def compile(self):
        return self.element_reader.compile() + super().compile()

    def read(self):
        return f"""
        {read_fNBytes()}
        {stream_data_token} pos + \\ stack: [end_pos]

        {read_uint32()} \\ stack: [end_pos, fTag]
        dup {kNewClassTag} =
        if
            drop
            begin
                {read_uint8()} dup 0 =
            until
            drop
        else
            drop
        then

        {self.element_reader.read_token}

        dup {stream_data_token} pos = invert
        if
            ." ObjectHeaderReader({self.name}): Invalid read length" .
            halt
        then
        drop
        """

    def data(self):
        return self.element_reader.data()

    def iter_subreaders(self):
        return [self.element_reader]


class CStyleArrayReader(IReader):
    def __init__(
        self, name: str, flat_size: int, element_reader: IReader, buffer_holder: BufferHolder
    ):
        super().__init__(name, buffer_holder)
        self.flat_size = flat_size
        self.element_reader = element_reader

        self.offsets_token = self.register_buffer("offsets", "q")

    def compile(self):
        res = self.element_reader.compile() + super().compile() + "\n"
        if self.flat_size < 0:
            res += f"0 {self.offsets_token} <- stack\n"
        return res

    def read(self):
        if self.flat_size >= 0:
            return f"""
            {debug_print(f'." CStyleArrayReader({self.name}): reading C-style array of flat_size={self.flat_size}" cr')}
            {debug_print('." - data(before): "')}
            {debug_print_input(stream_data_token)}
            {debug_print('." - stack(before): " .s cr')}

            {self.flat_size}
            {self.element_reader.read_many_token}
            drop

            {debug_print('." - data(after): "')}
            {debug_print_input(stream_data_token)}
            {debug_print('." - stack(after): " .s cr')}
            """

        return f"""\\ stack: []
        {debug_print(f'." CStyleArrayReader({self.name}): reading variable-size array" cr')}
        {debug_print_input(stream_data_token)}
        {debug_print(f'." {stream_data_token} pos: " {stream_data_token} pos . ." end_pos: " {stream_evt_end_pos_token} @ . cr')}
        {debug_print('." - stack: " .s cr')}

        {stream_evt_end_pos_token} @          \\ stack: [end_pos]

        dup {stream_data_token} pos =
        if
            drop
            0
        else
            {debug_print(f'." CStyleArrayReader({self.name}) begins read:" cr ." - data: "')}
            {debug_print_input(stream_data_token)}
            {debug_print('." - stack: " .s cr cr')}
            {self.element_reader.read_until_token} \\ stack: [count]
        then

        {debug_print(f'cr ." CStyleArrayReader({self.name}): finished reading elements, total count: " dup . cr')}
        {debug_print('." - stack: " .s cr')}

        {self.offsets_token} +<- stack

        {debug_print_input(stream_data_token)}
        {debug_print(f'{stream_data_token} pos . {stream_evt_end_pos_token} @ . cr')}
        """

    def read_many(self):
        if self.flat_size < 0:
            return f"""
            ." Calling CStyleArrayReader({self.name}).read_many with negative flat_size is not allowed" .
            halt
            """

        return f"""\\ stack: [count]
        dup 0 <
        if
            ." Calling CStyleArrayReader({self.name}).read_many with negative count is not allowed" .
            halt
        then

        dup 0 do
            {self.flat_size}
            {self.element_reader.read_many_token}
            drop
        loop
        """

    def read_until(self):
        return """
        ." CStyleArrayReader.read_until is not supported" .
        halt
        """

    def data(self):
        if self.flat_size >= 0:
            return self.element_reader.data()

        offsets = self.get_buffer(self.offsets_token)
        element_data = self.element_reader.data()
        return offsets, element_data

    def iter_subreaders(self):
        return [self.element_reader]


class EmptyReader(IReader):
    def read(self):
        return ""

    def data(self):
        return None
