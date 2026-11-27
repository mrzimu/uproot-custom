"""
Type stubs for uproot_custom.cpp.

At present, this module contains only type hints for C++ reader
classes used in uproot for parsing ROOT file formats.
"""

import numpy as np

class IReader:
    def data(self): ...

class UInt8Reader(IReader):
    def __init__(self, name: str) -> None: ...

class UInt16Reader(IReader):
    def __init__(self, name: str) -> None: ...

class UInt32Reader(IReader):
    def __init__(self, name: str) -> None: ...

class UInt64Reader(IReader):
    def __init__(self, name: str) -> None: ...

class Int8Reader(IReader):
    def __init__(self, name: str) -> None: ...

class Int16Reader(IReader):
    def __init__(self, name: str) -> None: ...

class Int32Reader(IReader):
    def __init__(self, name: str) -> None: ...

class Int64Reader(IReader):
    def __init__(self, name: str) -> None: ...

class DoubleReader(IReader):
    def __init__(self, name: str) -> None: ...

class FloatReader(IReader):
    def __init__(self, name: str) -> None: ...

class STLSeqReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
        element_reader: IReader,
    ) -> None: ...

class STLMapReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
        key_reader: IReader,
        value_reader: IReader,
    ) -> None: ...

class STLStringReader(IReader):
    def __init__(
        self,
        name: str,
        with_header: bool,
    ) -> None: ...

class TArrayCReader(IReader):
    def __init__(self, name: str) -> None: ...

class TArraySReader(IReader):
    def __init__(self, name: str) -> None: ...

class TArrayIReader(IReader):
    def __init__(self, name: str) -> None: ...

class TArrayLReader(IReader):
    def __init__(self, name: str) -> None: ...

class TArrayFReader(IReader):
    def __init__(self, name: str) -> None: ...

class TArrayDReader(IReader):
    def __init__(self, name: str) -> None: ...

class TStringReader(IReader):
    def __init__(self, name: str, with_header: bool) -> None: ...

class TObjectReader(IReader):
    def __init__(self, name: str, keep_data: bool, with_header: bool) -> None: ...

class GroupReader(IReader):
    def __init__(
        self,
        name: str,
        sub_readers: list[IReader],
    ) -> None: ...

class AnyClassReader(IReader):
    def __init__(
        self,
        name: str,
        sub_readers: list[IReader],
        with_header: bool,
    ) -> None: ...

class AnyPointerReader(IReader):
    def __init__(
        self,
        name: str,
        element_reader: IReader,
    ) -> None: ...

class CStyleArrayReader(IReader):
    def __init__(
        self,
        name: str,
        flat_size: int,
        element_reader: IReader,
    ) -> None: ...

class EmptyReader(IReader):
    def __init__(self, name: str) -> None: ...

def read_data(data: np.ndarray, offsets: np.ndarray, cursor_offset: int, reader: IReader): ...
