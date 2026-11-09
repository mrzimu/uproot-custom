"""
IR builder used by the reader frontend.

The reader frontend historically emitted the legacy 20-byte instruction
stream directly.  It now emits detree-vm's typed IR instead; this builder keeps
the small, expression-oriented surface the emitter was written against while
all control flow is structured (there are no labels or jumps).

Optimization does not happen here: `detree.compile` runs the detree-vm
optimizer and lowering after the frontend has produced the IR.
"""

from __future__ import annotations

from detree.ir import nodes
from detree.spec.isa import Op, Typecode


class _UnsupportedIR(Exception):
    """
    Internal: a legacy emitter operation that has no IR equivalent.
    """


_ARITHMETIC = {
    Op.ADD,
    Op.SUB,
    Op.MUL,
    Op.DIV_S,
    Op.DIV_U,
    Op.MOD_S,
    Op.MOD_U,
    Op.SHL,
    Op.SHR_S,
    Op.SHR_U,
    Op.AND,
    Op.OR,
    Op.XOR,
}
_COMPARISONS = {
    Op.CMP_EQ,
    Op.CMP_NE,
    Op.CMP_LT_S,
    Op.CMP_LE_S,
    Op.CMP_GT_S,
    Op.CMP_GE_S,
    Op.CMP_LT_U,
    Op.CMP_LE_U,
    Op.CMP_GT_U,
    Op.CMP_GE_U,
}
_UNARY = {Op.NEG, Op.NOT, Op.NOT_B}


def _value(value):
    """
    A register argument: IR expressions pass through; legacy ints are consts.
    """
    if isinstance(value, nodes.Expr):
        return value
    return nodes.Const(int(value))


class IRFunctionBuilder:
    """
    Build one detree-vm IR function with an emitter-friendly API.
    """

    def __init__(self, function: nodes.Function, program: nodes.Program):
        self.function = function
        self.program = program
        self._next_temp = 0
        self._next_local = 0

    # -- declarations ----------------------------------------------------
    def local(self, name: str) -> nodes.Local:
        if name not in self.function.params and name not in self.function.locals:
            self.function.locals.append(name)
        return nodes.Local(name)

    def temp(self) -> nodes.Local:
        name = f"__tmp{self._next_temp}"
        self._next_temp += 1
        return self.local(name)

    def reg(self):
        """
        The emitter's scratch register is just a fresh IR local.
        """
        return self.temp()

    def finish(self):
        """
        Kept for the emitter's explicit finalisation call.
        """

    # -- statements ------------------------------------------------------
    def emit(self, stmt, **operands):
        if isinstance(stmt, (Op, int)):
            return self.emit_op(stmt, **operands)
        self.function.body.append(stmt)
        return stmt

    def _emit_expr(self, op, rd, ra, rb):
        target = _value(rd)
        if op in _ARITHMETIC:
            self.emit(nodes.Assign(target, nodes.Binary(op, _value(ra), _value(rb))))
        elif op in _COMPARISONS:
            self.emit(nodes.Assign(target, nodes.Compare(op, _value(ra), _value(rb))))
        elif op in _UNARY:
            self.emit(nodes.Assign(target, nodes.Unary(op, _value(ra))))
        else:
            raise _UnsupportedIR(f"no expression lowering for opcode {op.name}")

    def emit_op(self, op, rd=0, ra=0, rb=0, imm1=0, imm2=0):
        """
        Lower one legacy opcode-shaped operation to an IR statement.
        """
        op = Op(op)

        if op == Op.CONST:
            self.emit(nodes.Assign(_value(rd), nodes.Const(int(imm1))))
        elif op == Op.CONST_F:
            width = 32 if imm2 == 32 else 64
            self.emit(nodes.Assign(_value(rd), nodes.ConstFloat(int(imm1), width)))
        elif op == Op.MOV:
            self.emit(nodes.Assign(_value(rd), _value(ra)))
        elif op in (Op.ZEXT8, Op.ZEXT16, Op.ZEXT32, Op.SEXT8, Op.SEXT16, Op.SEXT32):
            kind = "zext" if op.name.startswith("ZEXT") else "sext"
            width = int(op.name[4:])
            self.emit(nodes.Assign(_value(rd), nodes.Cast(kind, width, _value(ra))))
        elif op in _ARITHMETIC or op in _COMPARISONS or op in _UNARY:
            self._emit_expr(op, rd, ra, rb)
        elif op in (Op.SREAD, Op.SREAD_FNB, Op.SREAD_VERSION, Op.SREAD_CSTR):
            if op == Op.SREAD:
                value = nodes.StreamRead(Typecode(int(imm1)))
            elif op == Op.SREAD_FNB:
                value = nodes.StreamReadFNB()
            elif op == Op.SREAD_VERSION:
                value = nodes.StreamReadVersion()
            else:
                value = nodes.StreamReadCString()
            self.emit(nodes.Assign(_value(rd), value))
        elif op == Op.CURSOR:
            self.emit(nodes.Assign(_value(rd), nodes.Cursor()))
        elif op == Op.ENTRIES:
            self.emit(nodes.Assign(_value(rd), nodes.Entries()))
        elif op == Op.INIT_OFFSET:
            self.emit(nodes.Assign(_value(rd), nodes.InitOffset()))
        elif op == Op.DATA_SIZE:
            self.emit(nodes.Assign(_value(rd), nodes.DataSize()))
        elif op == Op.OFFSET_AT:
            self.emit(nodes.Assign(_value(rd), nodes.OffsetAt(_value(ra))))
        elif op == Op.OFFSET_SEEK:
            self.emit(nodes.Assign(_value(rd), nodes.OffsetSeek(_value(ra))))
        elif op == Op.EVENT_END:
            self.emit(nodes.Assign(_value(rd), nodes.EventEnd()))
        elif op == Op.BUF_LAST:
            self.emit(nodes.Assign(_value(rd), nodes.BufferLast(int(imm1))))
        elif op == Op.BUF_LEN:
            self.emit(nodes.Assign(_value(rd), nodes.BufferLen(int(imm1))))
        elif op == Op.STATE_GET:
            self.emit(nodes.Assign(_value(rd), nodes.StateGet(int(imm1))))
        elif op == Op.STATE_SET:
            self.emit(nodes.Assign(nodes.StateSlot(int(imm1)), _value(ra)))
        elif op == Op.STATE_IADD:
            current = nodes.StateGet(int(imm1))
            value = nodes.Binary(Op.ADD, current, nodes.Const(int(imm2)))
            self.emit(nodes.Assign(nodes.StateSlot(int(imm1)), value))
        elif op == Op.STR_CONST:
            self.emit(nodes.Assign(_value(rd), nodes.StrConst(int(imm1))))
        elif op == Op.STR_EQ:
            self.emit(nodes.Assign(_value(rd), nodes.StrEq(_value(ra), _value(rb))))
        elif op == Op.STR_STORE:
            self.emit(nodes.Assign(nodes.StateSlot(int(imm1)), _value(ra)))
        elif op == Op.STR_LOAD:
            self.emit(nodes.Assign(_value(rd), nodes.StateGet(int(imm1))))
        elif op == Op.REF_HAS:
            self.emit(nodes.Assign(_value(rd), nodes.RefHas(_value(ra))))
        elif op == Op.REF_GET_OBJ:
            self.emit(nodes.Assign(_value(rd), nodes.RefGetObj(_value(ra))))
        elif op == Op.REF_GET_CLASS:
            self.emit(nodes.Assign(_value(rd), nodes.RefGetClass(_value(ra))))
        elif op == Op.REF_COUNT:
            self.emit(nodes.Assign(_value(rd), nodes.RefCount()))
        elif op == Op.REF_SET_OBJ:
            self.emit(nodes.RefSetObj(_value(ra), _value(rb)))
        elif op == Op.REF_SET_CLASS:
            self.emit(nodes.RefSetClass(_value(ra), _value(rb)))
        elif op == Op.BUF_APPEND:
            self.emit(nodes.BufferAppend(int(imm1), _value(ra)))
        elif op == Op.BUF_APPEND_CONST:
            self.emit(nodes.BufferAppendConst(int(imm1), int(imm2)))
        elif op == Op.BUF_APPEND_OFFSET:
            self.emit(nodes.BufferAppendOffset(int(imm1), _value(ra)))
        elif op == Op.BUF_APPEND_LEN:
            self.emit(nodes.BufferAppendLen(int(imm1), int(imm2)))
        elif op == Op.BUF_RESERVE:
            self.emit(nodes.BufferReserve(int(imm1), _value(ra)))
        elif op == Op.READ_BULK:
            self.emit(nodes.ReadBulk(int(imm1), Typecode(int(imm2)), _value(ra)))
        elif op == Op.READ_STRIDED:
            self.emit(
                nodes.ReadStrided(int(imm1), Typecode(int(imm2)), _value(ra), _value(rb))
            )
        elif op == Op.READ_FIELDS:
            self.emit(nodes.ReadFields(int(imm1), _value(ra)))
        elif op == Op.READ_APPEND:
            self.emit(nodes.ReadAppend(int(imm1), Typecode(int(imm2))))
        elif op == Op.SKIP:
            self.emit(nodes.Skip(int(imm1)))
        elif op == Op.SKIP_R:
            self.emit(nodes.SkipR(_value(ra)))
        elif op == Op.SKIP_FNB:
            self.emit(nodes.SkipFNB())
        elif op == Op.SKIP_VERSION:
            self.emit(nodes.SkipVersion())
        elif op == Op.SKIP_TOBJECT:
            self.emit(nodes.SkipTObject())
        elif op == Op.SKIP_OBJHDR:
            self.emit(nodes.SkipObjHdr())
        elif op == Op.SKIP_CSTR:
            self.emit(nodes.SkipCStr())
        elif op == Op.SET_CURSOR:
            self.emit(nodes.SetCursor(_value(ra)))
        elif op == Op.RET:
            self.emit(nodes.Return(None if not ra else _value(ra)))
        elif op in (Op.NOP, Op.LINE, Op.DEBUG_PRINT):
            return
        else:
            raise _UnsupportedIR(f"no statement lowering for opcode {op.name}")

    # -- expression helpers ---------------------------------------------
    def const(self, value):
        return nodes.Const(int(value))

    def const_into(self, target, value):
        self.emit(nodes.Assign(_value(target), nodes.Const(int(value))))

    def mov(self, target, value):
        self.emit(nodes.Assign(_value(target), _value(value)))

    def cursor(self, dst=None):
        return nodes.Cursor()

    def entries(self, dst=None):
        return nodes.Entries()

    def init_offset(self, dst=None):
        return nodes.InitOffset()

    def data_size(self, dst=None):
        return nodes.DataSize()

    def read_scalar(self, typecode, dst=None):
        return nodes.StreamRead(Typecode(int(typecode)))

    def read_fnb(self, dst=None):
        return nodes.StreamReadFNB()

    def read_version(self, dst=None):
        return nodes.StreamReadVersion()

    def read_cstr(self, dst=None):
        return nodes.StreamReadCString()

    def buf_last(self, buf):
        return nodes.BufferLast(int(buf))

    def buf_len(self, buf):
        return nodes.BufferLen(int(buf))

    def buf_append(self, buf, value):
        return self.emit(nodes.BufferAppend(int(buf), _value(value)))

    def buf_append_const(self, buf, value):
        return self.emit(nodes.BufferAppendConst(int(buf), int(value)))

    def buf_append_offset(self, buf, value):
        return self.emit(nodes.BufferAppendOffset(int(buf), _value(value)))

    def buf_append_len(self, dst, src):
        return self.emit(nodes.BufferAppendLen(int(dst), int(src)))

    def read_bulk(self, buf, typecode, count):
        return self.emit(nodes.ReadBulk(int(buf), Typecode(int(typecode)), _value(count)))

    def read_strided(self, buf, typecode, count, stride):
        return self.emit(
            nodes.ReadStrided(int(buf), Typecode(int(typecode)), _value(count), _value(stride))
        )

    def read_fields(self, layout, count):
        return self.emit(nodes.ReadFields(int(layout), _value(count)))

    def read_append(self, buf, typecode):
        return self.emit(nodes.ReadAppend(int(buf), Typecode(int(typecode))))

    def skip(self, nbytes):
        return self.emit(nodes.Skip(int(nbytes)))

    def skip_reg(self, value):
        return self.emit(nodes.SkipR(_value(value)))

    def skip_version(self):
        return self.emit(nodes.SkipVersion())

    def skip_fnb(self):
        return self.emit(nodes.SkipFNB())

    def skip_tobject(self):
        return self.emit(nodes.SkipTObject())

    def skip_objhdr(self):
        return self.emit(nodes.SkipObjHdr())

    def skip_cstr(self):
        return self.emit(nodes.SkipCStr())

    def set_cursor(self, value):
        return self.emit(nodes.SetCursor(_value(value)))

    def offset_seek(self, value):
        return nodes.OffsetSeek(_value(value))

    def state_get(self, slot):
        return nodes.StateGet(int(slot))

    def state_set(self, slot, value):
        return self.emit(nodes.Assign(nodes.StateSlot(int(slot)), _value(value)))

    def state_iadd(self, slot, value):
        current = nodes.StateGet(int(slot))
        return self.emit(
            nodes.Assign(
                nodes.StateSlot(int(slot)),
                nodes.Binary(Op.ADD, current, nodes.Const(int(value))),
            )
        )

    def str_const(self, ident):
        return nodes.StrConst(int(ident))

    def str_load(self, slot):
        return nodes.StateGet(int(slot))

    def str_store(self, slot, value):
        return self.emit(nodes.Assign(nodes.StateSlot(int(slot)), _value(value)))

    def ref_has(self, value):
        return nodes.RefHas(_value(value))

    def ref_get_obj(self, value):
        return nodes.RefGetObj(_value(value))

    def ref_get_class(self, value):
        return nodes.RefGetClass(_value(value))

    def ref_count(self):
        return nodes.RefCount()

    def ref_set_obj(self, tag, value):
        return self.emit(nodes.RefSetObj(_value(tag), _value(value)))

    def ref_set_class(self, tag, value):
        return self.emit(nodes.RefSetClass(_value(tag), _value(value)))

    def assert_str_eq(self, left, right, message):
        return self.emit(nodes.AssertStrEq(_value(left), _value(right), message))

    def throw(self, message):
        return self.emit(nodes.Throw(message))

    def call(self, func, arg=None):
        callee = self.program.functions[int(func)]
        if callee.arity == 0:
            argument = None
        else:
            argument = _value(arg)
        if callee.result == nodes.VOID:
            self.emit(nodes.CallStmt(None, int(func), argument))
            return nodes.Const(0)
        return nodes.Call(int(func), argument)

    def ret(self, value=None):
        if value is None:
            return self.emit(nodes.Return(None))
        if isinstance(value, int) and value == 0:
            return self.emit(nodes.Return(None))
        return self.emit(nodes.Return(_value(value)))

    # -- structured control flow ----------------------------------------
    def block(self):
        return _Block(self)

    def if_(self, cond, then_body, else_body=()):
        return self.emit(nodes.If(cond, list(then_body), list(else_body)))

    def while_(self, cond, body):
        return self.emit(nodes.While(cond, list(body)))

    def for_range(self, var, start, stop, step, body):
        self.local(var)
        return self.emit(nodes.ForRange(var, start, stop, step, list(body)))


class _Block:
    """
    Capture statements emitted while building a nested body.
    """

    def __init__(self, builder: IRFunctionBuilder):
        self.builder = builder
        self.statements = []

    def __enter__(self):
        self._saved = self.builder.function.body
        self.builder.function.body = self.statements
        return self

    def __exit__(self, exc_type, exc, tb):
        self.builder.function.body = self._saved
        return False


__all__ = ["IRFunctionBuilder"]
