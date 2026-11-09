"""
The declarative reader contract: fields, defaults, and the @reader checks.
"""

from __future__ import annotations

import numpy as np
import pytest

from uproot_custom.detree.builtin import PrimitiveReader, TArrayReader
from uproot_custom.detree.compiler.frontend import describe_reader
from uproot_custom.detree.decl import (
    Buffer,
    Const,
    Reader,
    ReaderContractError,
    State,
    reader,
)


@reader
class _Limited(Reader):
    level = Const(0, type=int, ge=0, le=4)
    values = Buffer("i")

    def read(self, stream):
        self.values.append(self.level)

    def data(self):
        return np.asarray(self.values)


@reader
class _Choice(Reader):
    mode = Const("a", type=str, choices=("a", "b"))
    values = Buffer("i")

    def read(self, stream):
        self.values.append(stream.read_int32())

    def data(self):
        return np.asarray(self.values)


@reader
class _Counter(Reader):
    step = Const(1, type=int)
    seen = State(int, 0)
    values = Buffer("i")

    def read(self, stream):
        self.seen = self.seen + self.step
        self.values.append(stream.read_int32())

    def data(self):
        return np.asarray(self.values), self.seen


@reader
class _Required(Reader):
    typecode = Const(type=str, choices=("b", "B", "h", "H", "i", "I", "q", "Q", "f", "d"))
    values = Buffer(from_const="typecode")

    def read(self, stream):
        stream.read_into(self.values)

    def data(self):
        return np.asarray(self.values)


class _Undecorated(Reader):
    values = Buffer("i")

    def read(self, stream):
        self.values.append(stream.read_int32())

    def data(self):
        return np.asarray(self.values)


# -- Const ---------------------------------------------------------------------
def test_const_sets_a_default():
    assert _Limited("a").level == 0
    assert _Counter("b").step == 1


def test_const_rejects_a_value_below_its_lower_bound():
    with pytest.raises(ValueError, match="< 0"):
        _Limited("a", level=-1)


def test_const_rejects_a_value_above_its_upper_bound():
    with pytest.raises(ValueError, match="> 4"):
        _Limited("a", level=5)


def test_const_rejects_a_value_outside_its_choices():
    with pytest.raises(ValueError, match="not in"):
        _Choice("a", mode="c")
    assert _Choice("a", mode="b").mode == "b"


def test_const_accepts_numpy_integers():
    assert _Limited("a", level=np.int64(3)).level == 3
    assert _Counter("b", step=np.int32(2)).step == 2


def test_const_rejects_a_bool_where_an_int_is_expected():
    with pytest.raises(TypeError, match="expected int"):
        _Counter("b", step=True)


def test_const_rejects_a_missing_required_argument():
    with pytest.raises(TypeError, match="missing required argument"):
        _Required("a")


def test_const_rejects_an_unknown_type():
    with pytest.raises(TypeError, match="Const's type can only be"):
        Const(0, type=float)


# -- Buffer --------------------------------------------------------------------
def test_buffer_from_const_uses_the_declared_typecode():
    reader = _Required("a", typecode="d")
    assert reader.values.typecode == "d"
    assert reader.values.dtype == np.dtype("float64")


def test_buffer_from_const_follows_the_constant():
    assert _Required("a", typecode="B").values.dtype == np.dtype("uint8")
    assert _Required("a", typecode="q").values.dtype == np.dtype("int64")


def test_buffer_requires_a_typecode_or_a_constant():
    with pytest.raises(TypeError, match="pass a type or name a Const"):
        Buffer()


def test_buffer_rejects_a_platform_dependent_typecode():
    with pytest.raises(TypeError, match="unsupported typecode"):
        Buffer("l")


def test_buffer_accepts_a_numpy_dtype():
    assert Buffer(np.int32).typecode == "i"
    assert Buffer(np.uint64).typecode == "Q"
    assert Buffer(np.float32).typecode == "f"
    assert Buffer(np.bool_).typecode == "B"
    assert Buffer(np.dtype("int16")).typecode == "h"
    assert Buffer(np.dtype("<f8")).typecode == "d"


def test_buffer_accepts_a_dtype_string():
    assert Buffer("int64").typecode == "q"
    assert Buffer("uint8").typecode == "B"
    assert Buffer("float64").typecode == "d"
    assert Buffer("<u4").typecode == "I"
    assert Buffer(">i2").typecode == "h"


def test_buffer_rejects_an_unsupported_dtype():
    with pytest.raises(TypeError, match="unsupported dtype"):
        Buffer(np.complex128)
    with pytest.raises(TypeError, match="is not a typecode or a NumPy dtype"):
        Buffer(object())


def test_builtin_readers_resolve_their_element_typecode():
    assert PrimitiveReader("p", typecode="f").values.dtype == np.dtype("float32")
    assert TArrayReader("t", typecode="q").values.dtype == np.dtype("int64")


# -- State ---------------------------------------------------------------------
def test_state_starts_at_its_declared_value_and_resets():
    counter = _Counter("c")
    assert counter.seen == 0

    counter.seen = 7
    counter.values.append(1)
    assert counter.seen == 7
    assert len(counter.values) == 1

    counter.reset()
    assert counter.seen == 0
    assert len(counter.values) == 0


def test_state_accepts_a_name_slot():
    class _Named(Reader):
        name = State(str, None)

        def read(self, stream):
            pass

        def data(self):
            return None

    _Named = reader(_Named)
    named = _Named("n")
    assert named.name is None
    named.name = "x"
    named.reset()
    assert named.name is None


# -- describe_reader -----------------------------------------------------------
def test_describe_reader_ignores_the_current_state_value():
    counter = _Counter("c")
    before = describe_reader(counter)
    counter.seen = 123
    assert describe_reader(counter) == before


def test_describe_reader_separates_different_constants():
    assert describe_reader(PrimitiveReader("p", typecode="i")) != describe_reader(
        PrimitiveReader("p", typecode="d")
    )


def test_describe_reader_is_stable_across_equal_trees():
    first = describe_reader(PrimitiveReader("p", typecode="d"))
    second = describe_reader(PrimitiveReader("p", typecode="d"))
    assert first == second


# -- the @reader checks --------------------------------------------------------
def test_reader_rejects_an_overridden_init():
    with pytest.raises(ReaderContractError, match="do not override __init__"):

        @reader
        class _WithInit(Reader):
            values = Buffer("i")

            def __init__(self, name):
                super().__init__(name)

            def read(self, stream):
                pass

            def data(self):
                return None


def test_reader_requires_read_and_data():
    with pytest.raises(ReaderContractError, match="must define read"):
        reader(type("_NoRead", (Reader,), {"data": lambda self: None}))

    with pytest.raises(ReaderContractError, match="must define data"):
        reader(type("_NoData", (Reader,), {"read": lambda self, stream: None}))


def test_reader_rejects_an_assignment_to_a_plain_attribute():
    with pytest.raises(ReaderContractError, match="self.other is assigned"):

        @reader
        class _BadAssign(Reader):
            values = Buffer("i")

            def read(self, stream):
                self.other = 1

            def data(self):
                return None


def test_reader_rejects_a_banned_ast_node():
    with pytest.raises(ReaderContractError, match="ListComp"):

        @reader
        class _Banned(Reader):
            values = Buffer("i")

            def read(self, stream):
                _ = [value for value in range(3)]

            def data(self):
                return None


def test_reader_rejects_a_child_held_as_a_class_attribute():
    with pytest.raises(ReaderContractError, match="sub-reader is a field"):

        @reader
        class _HeldChild(Reader):
            element = PrimitiveReader("e", typecode="i")

            def read(self, stream):
                pass

            def data(self):
                return None


def test_a_decorated_reader_is_marked_compilable():
    assert type(PrimitiveReader("p", typecode="i")).__dict__.get("__reader_checked__") is True


def test_an_undecorated_reader_is_not_marked():
    assert _Undecorated.__dict__.get("__reader_checked__", False) is False
