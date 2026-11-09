"""
The native frontend: reader trees -> detree-vm IR -> optimized module bytes.
"""

from __future__ import annotations

import detree
import pytest

from uproot_custom.detree import builtin
from uproot_custom.detree.compiler import frontend
from uproot_custom.detree.compiler.frontend import (
    UnsupportedNode,
    compile_reader,
    describe_reader,
)
from uproot_custom.detree.decl import Buffer, Reader


def _prim(name="p", typecode="i"):
    return builtin.PrimitiveReader(name, typecode=typecode)


#: one reader of every built-in kind, built fresh for each test
READERS = {
    "primitive": lambda: _prim(),
    "tobject": lambda: builtin.TObjectReader("t", keep_data=True),
    "tstring": lambda: builtin.TStringReader("s", with_header=False),
    "stlstring": lambda: builtin.STLStringReader("s", with_header=True),
    "tarray": lambda: builtin.TArrayReader("a", typecode="d"),
    "stlseq": lambda: builtin.STLSeqReader("v", with_header=True, element=_prim("e")),
    "stlmap": lambda: builtin.STLMapReader(
        "m", with_header=True, key=_prim("k"), value=_prim("v", "d")
    ),
    "group": lambda: builtin.GroupReader("g", elements=[_prim("a"), _prim("b", "B")]),
    "anyclass": lambda: builtin.AnyClassReader("c", elements=[_prim("a")]),
    "anypointer": lambda: builtin.AnyPointerReader("p", element=builtin.EmptyReader("e")),
    "cstyle": lambda: builtin.CStyleArrayReader("c", flat_size=3, element=_prim("e")),
    "cstyle_jagged": lambda: builtin.CStyleArrayReader("c", flat_size=-1, element=_prim("e")),
    "empty": lambda: builtin.EmptyReader("e"),
}


class _Undecorated(Reader):
    values = Buffer("i")

    def read(self, stream):
        self.values.append(stream.read_int32())


@pytest.mark.parametrize("name", sorted(READERS))
def test_every_builtin_reader_compiles_and_validates(name):
    raw, signature = compile_reader(READERS[name]())

    assert isinstance(raw, bytes) and raw
    assert raw[:4] == detree.spec.isa.MAGIC
    assert isinstance(signature, str) and signature

    module = detree.spec.module.Module.from_bytes(raw)
    detree.spec.validate.validate_module(module)


def test_compile_reader_is_deterministic():
    first, first_signature = compile_reader(_prim())
    second, second_signature = compile_reader(_prim())

    assert first == second
    assert first_signature == second_signature


def test_structurally_equal_trees_share_a_signature():
    assert describe_reader(_prim()) == describe_reader(_prim())
    assert describe_reader(_prim("other")) == describe_reader(_prim())


def test_the_root_read_function_is_the_entry():
    raw, _ = compile_reader(_prim())
    module = detree.spec.module.Module.from_bytes(raw)

    assert module.funcs[module.entry].name == "root.read"


def test_the_four_entry_points_are_generated(monkeypatch):
    # The frontend emits all four entry points; the optimizer then drops the
    # ones a branch cannot reach, so this asserts on the unoptimized module.
    monkeypatch.setenv("DETREE_OPT", "0")
    raw, _ = compile_reader(_prim())
    module = detree.spec.module.Module.from_bytes(raw)

    assert {func.name for func in module.funcs} >= {
        "root.read",
        "root.read_many",
        "root.read_until",
        "root.read_many_memberwise",
    }


def test_detree_optimizer_fuses_a_read_append():
    raw, _ = compile_reader(_prim(typecode="d"))
    module = detree.spec.module.Module.from_bytes(raw)

    read = next(func for func in module.funcs if func.name == "root.read")
    operators = [ins.op for ins in module.code[read.code_off : read.end]]
    assert detree.spec.isa.Op.READ_APPEND in operators


def test_the_module_declares_the_reader_buffers():
    raw, _ = compile_reader(_prim(typecode="d"))
    module = detree.spec.module.Module.from_bytes(raw)

    assert [decl.dtype for decl in module.buffers] == ["float64"]
    assert module.buffers[0].kind == detree.spec.isa.BufferKind.DATA


def test_offsets_buffers_keep_their_kind():
    reader = builtin.STLSeqReader("v", with_header=True, element=_prim("e"))
    raw, _ = compile_reader(reader)
    module = detree.spec.module.Module.from_bytes(raw)

    offsets = next(decl for decl in module.buffers if decl.name.endswith(":offsets"))
    assert offsets.kind == detree.spec.isa.BufferKind.OFFSETS
    assert offsets.dtype == "int64"


def test_compile_reader_delegates_to_detree_compile(monkeypatch):
    calls = []
    original = frontend.detree_compile

    def wrapped(program):
        calls.append(program)
        return original(program)

    monkeypatch.setattr(frontend, "detree_compile", wrapped)
    compile_reader(_prim())

    assert len(calls) == 1
    assert isinstance(calls[0], detree.ir.nodes.Program)


def test_an_undecorated_reader_is_refused():
    with pytest.raises(UnsupportedNode, match="@reader"):
        compile_reader(_Undecorated("x"))
