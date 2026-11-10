from __future__ import annotations

import ast
import inspect
import os
import textwrap
from collections.abc import Generator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Callable, Literal

from detree import compile as detree_compile
from detree.ir import nodes
from detree.spec.isa import BufferKind, Op, Typecode

from uproot_custom.consts import TYPECODE
from uproot_custom.detree.bufferproxy import BufferProxy
from uproot_custom.detree.compiler.ir_builder import IRFunctionBuilder
from uproot_custom.detree.decl import Buffer, Child, ChildList, Const, Reader, State
from uproot_custom.detree.stream import COUNTED_CONTEXT

if not hasattr(nodes, "FNBegin"):  # pragma: no cover - depends on the installed detree-vm
    raise ImportError(
        "uproot-custom needs a detree-vm with byte-count frames "
        "(FNB_BEGIN/FNB_END); upgrade detree-vm"
    )

STREAM_READS = {
    "read_uint8": Typecode.UINT8,
    "read_uint16": Typecode.UINT16,
    "read_uint32": Typecode.UINT32,
    "read_uint64": Typecode.UINT64,
    "read_int8": Typecode.INT8,
    "read_int16": Typecode.INT16,
    "read_int32": Typecode.INT32,
    "read_int64": Typecode.INT64,
    "read_float": Typecode.FLOAT32,
    "read_double": Typecode.FLOAT64,
    "read_bool": Typecode.UINT8,
}

#: buffer declaration typecode (a ``struct`` char, the module's ``TC``) -> the
#: machine's numeric ``Typecode``, which is what an instruction's ``imm2`` holds.
#: The two numberings are deliberately separate: buffers are declared with the
#: same chars ``array.array`` uses, instructions with the ISA enum.
BUFFER_TYPECODES = {
    "B": Typecode.UINT8,
    "H": Typecode.UINT16,
    "I": Typecode.UINT32,
    "Q": Typecode.UINT64,
    "b": Typecode.INT8,
    "h": Typecode.INT16,
    "i": Typecode.INT32,
    "q": Typecode.INT64,
    "f": Typecode.FLOAT32,
    "d": Typecode.FLOAT64,
}

STREAM_SKIPS = {
    "skip_fNBytes": Op.SKIP_FNB,
    "skip_fVersion": Op.SKIP_VERSION,
    "skip_TObject": Op.SKIP_TOBJECT,
    "skip_obj_header": Op.SKIP_OBJHDR,
    "skip_null_terminated_string": Op.SKIP_CSTR,
}

#: struct char -> numpy dtype name used by a detree-vm buffer declaration.
BUFFER_DTYPES = {
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

BUFFER_KINDS = {
    "data": BufferKind.DATA,
    "offsets": BufferKind.OFFSETS,
}

BINARY_OPS = {
    ast.Add: Op.ADD,
    ast.Sub: Op.SUB,
    ast.Mult: Op.MUL,
    ast.FloorDiv: Op.DIV_S,
    ast.Div: Op.DIV_S,
    ast.Mod: Op.MOD_S,
    ast.LShift: Op.SHL,
    ast.RShift: Op.SHR_S,
    ast.BitAnd: Op.AND,
    ast.BitOr: Op.OR,
    ast.BitXor: Op.XOR,
}

COMPARE_CMPS = {
    ast.Eq: Op.CMP_EQ,
    ast.NotEq: Op.CMP_NE,
    ast.Lt: Op.CMP_LT_S,
    ast.LtE: Op.CMP_LE_S,
    ast.Gt: Op.CMP_GT_S,
    ast.GtE: Op.CMP_GE_S,
    ast.Is: Op.CMP_EQ,
    ast.IsNot: Op.CMP_NE,
}

ENTRY_METHODS = ("read", "read_many", "read_until", "read_many_memberwise")
TYPE_ENTRY_METHODS = Literal["read", "read_many", "read_until", "read_many_memberwise"]


class _Unsupported(Exception):
    """
    Internal: a construct the frontend cannot express.
    """


class UnsupportedNode(Exception):
    """
    A construct the frontend cannot express as bytecode.

    Raised by `uproot_custom.detree.compiler.frontend.compile_reader`.  A
    reader that cannot be compiled cannot be used by the detree backend; there
    is no fallback to another backend, so this is a user-visible error.
    """

    def __init__(self, reason, path=None):
        self.reason = reason
        self.path = path
        where = f" at {path}" if path else ""
        super().__init__(f"{reason}{where}")


def _is_reader(value):
    return isinstance(value, Reader)


def _buffer_items(reader: Reader) -> Generator[tuple[str, TYPECODE, tuple]]:
    for field in reader.__fields__:
        if isinstance(field, Buffer):
            buffer_proxy: BufferProxy = getattr(reader, field.name)
            # ``BufferProxy`` holds the typecode after ``from_const`` is
            # resolved; ``field.typecode`` is None for those buffers.
            yield field.name, buffer_proxy.typecode, buffer_proxy.init


def _reader_children(reader: Reader) -> Generator[tuple[str, Reader, str]]:
    for field in reader.__fields__:
        if isinstance(field, Child):
            yield field.name, getattr(reader, field.name), f"/{field.name}"
        elif isinstance(field, ChildList):
            for idx, item in enumerate(getattr(reader, field.name)):
                yield field.name, item, f"/{field.name}/{idx}"


def describe_reader(reader: Reader, path: str = "root"):
    """
    A structural signature: class, constants, buffers and children.

    Fields are walked in `declaration` order, so the signature does not depend
    on how a constructor happened to assign attributes.  A state is described
    by its declared default -- what the module seeds the slot with -- so the
    signature of a reader tree is the same before and after a run, and a reader
    reused across baskets stays one cache entry.
    """
    name = type(reader).__module__ + "." + type(reader).__qualname__
    parts = []
    for field in reader.__fields__:
        value = getattr(reader, field.name)
        if isinstance(field, Const):
            parts.append(f"{field.name}={value!r}")
        elif isinstance(field, State):
            # By the *declared* default, not the current value: a state is
            # per-basket, so after a run the instance holds that run's final
            # value while the module still seeds the slot with the default.
            # Reading the instance here made the signature change after every
            # basket, and a cache miss recompiled a byte-identical module.
            parts.append(f"{field.name}!={field.init!r}")
        elif isinstance(field, Buffer):
            parts.append(f"{field.name}:{value.dtype}:{list(value.init)!r}")
        elif isinstance(field, Child):
            parts.append(describe_reader(value, f"{path}/{field.name}"))
        elif isinstance(field, ChildList):
            inner = ",".join(
                describe_reader(item, f"{path}/{field.name}/{index}")
                for index, item in enumerate(value)
            )
            parts.append(f"{field.name}[{inner}]")
    return f"{name}({';'.join(parts)})"


@dataclass
class _FuncSlot:
    """
    One IR function, declared in reader traversal order.
    """

    id: int
    path: str
    method: str
    arity: int
    param: str | None = None
    function: nodes.Function = dataclass_field(default=None)

    @property
    def name(self):
        if self.path == "root":
            return f"root.{self.method}"
        return f"{self.path}.{self.method}"


class _Compiler:
    """
    Collects the declarations and IR functions of one reader tree.
    """

    def __init__(self, reader: Reader):
        self.root = reader
        self.program = nodes.Program()
        self.slots: list[_FuncSlot] = []
        self.slot_by_key: dict[tuple[str, str], _FuncSlot] = {}
        self.buffer_by_key: dict[str, int] = {}
        self.state_by_key: dict[str, int] = {}
        self.constant_ids: dict[str, int] = {}
        self.compiled: set[tuple[str, str]] = set()

        self._collect(reader, "root")

    # -- registration -----------------------------------------------------
    def _collect(self, reader: Reader, path: str):
        for attr, typecode, init in _buffer_items(reader):
            key = f"{path}:{attr}"
            if key in self.buffer_by_key:
                raise UnsupportedNode(f"duplicate buffer {key}", path)
            dtype = BUFFER_DTYPES.get(typecode)
            if dtype is None:
                raise UnsupportedNode(f"buffer {key}: unsupported typecode {typecode!r}", path)
            proxy = getattr(reader, attr)
            kind = BUFFER_KINDS[getattr(proxy, "kind", "data")]
            self.buffer_by_key[key] = len(self.program.buffers)
            self.program.buffers.append(
                nodes.Buffer(name=key, dtype=dtype, kind=kind, init=tuple(init))
            )

        for field in reader.__fields__:
            if not isinstance(field, State):
                continue

            key = f"{path}:{field.name}"
            if key in self.state_by_key:
                raise UnsupportedNode(f"duplicate state {key}", path)

            init = -1 if field.init is None else field.init
            if isinstance(init, str):
                # A name slot starts at an arena id.  Constants are seeded into
                # the lowerer's arena in declaration order, so the constant id
                # is the initial arena id.
                init = self.constant(init)
            self.state_by_key[key] = len(self.program.states)
            self.program.states.append(
                nodes.State(
                    name=key,
                    init=int(init),
                    type="name" if field.is_string else "i64",
                )
            )

        for method in ENTRY_METHODS:
            self._declare(path, method)

        for _, child, suffix in _reader_children(reader):
            self._collect(child, path + suffix)

    def _declare(self, path: str, method: str, arity: int | None = None):
        key = (path, method)
        slot = self.slot_by_key.get(key)
        if slot is None:
            if arity is None:
                arity = 0 if method == "read" else 1
            param = None
            if arity == 1:
                param = "end_pos" if method == "read_until" else "count"
            slot = _FuncSlot(
                id=len(self.slots),
                path=path,
                method=method,
                arity=arity,
                param=param,
            )
            slot.function = nodes.Function(
                name=slot.name,
                arity=arity,
                params=() if arity == 0 else (param,),
                body=[],
                result=nodes.VOID if method == "read" else nodes.I64,
            )
            self.slot_by_key[key] = slot
            self.slots.append(slot)
            self.program.functions.append(slot.function)
        return slot

    def func_id(self, path: str, method: str):
        return self._declare(path, method).id

    def buffer_id(self, path: str, attr: str):
        try:
            return self.buffer_by_key[f"{path}:{attr}"]
        except KeyError as err:
            raise _Unsupported(f"unknown buffer {attr!r}") from err

    def state_id(self, path: str, name: str):
        try:
            return self.state_by_key[f"{path}:{name}"]
        except KeyError as err:
            raise _Unsupported(f"unknown state {name!r}") from err

    def constant(self, text: str) -> int:
        ident = self.constant_ids.get(text)
        if ident is None:
            ident = len(self.program.constants)
            self.program.constants.append(nodes.Constant(text))
            self.constant_ids[text] = ident
        return ident

    def new_function(self, path: str, method: str, arity: int, param: str | None = None):
        slot = self._declare(path, method, arity)
        if slot.function.body:
            raise _Unsupported(f"{path}.{method} compiled twice")
        if arity == 1 and param is not None:
            slot.function.params = (param,)
        return IRFunctionBuilder(slot.function, self.program)

    def build(self):
        for slot in self.slots:
            if not slot.function.body:
                raise UnsupportedNode(f"{slot.name}: no IR emitted", slot.path)
        self.program.entry = self.func_id("root", "read")
        return detree_compile(self.program)


def _source_of(function: Callable):
    try:
        source = textwrap.dedent(inspect.getsource(function))
    except (OSError, TypeError) as err:
        raise _Unsupported(f"source is not available ({err})") from None

    tree = ast.parse(source)
    if not tree.body or not isinstance(tree.body[0], ast.FunctionDef):
        raise _Unsupported("not a plain function definition")
    return source, tree.body[0]


class _MethodEmitter:
    """
    Translate one Python method body into bytecode.
    """

    def __init__(self, compiler: _Compiler, reader: Reader, path: str, method: str):
        self.compiler = compiler
        self.reader = reader
        self.path = path
        self.method = method

        self.cls = type(reader)
        self.fn: IRFunctionBuilder = None
        self.vars: dict[str, nodes.Local] = {}
        self.state_fields = {f.name: f for f in reader.__fields__ if isinstance(f, State)}
        self.const_fields = {f.name for f in reader.__fields__ if isinstance(f, Const)}
        self.childlist_fields = {f.name for f in reader.__fields__ if isinstance(f, ChildList)}

        # (variable, path) while a children loop is being unrolled
        self.loop_var = None

        # True while an expression statement's value is being thrown away
        self.discard_result = False

        # Counted regions opened but not closed yet; `FNBEGIN`/`FNEND` pair up
        # inside the machine, so this is only a compile-time sanity check.
        self.nb_depth = 0

        # True while an `if`/`while` condition is being built: a counted region
        # opens with a statement, which cannot live inside a condition.
        self.in_condition = False

    # -- entry ------------------------------------------------------------
    def emit(self):
        function: Callable = getattr(self.cls, self.method)

        # check whether the method is overridden
        if function is getattr(Reader, self.method, None):
            return False

        # check the function signature for expected arguments (self, stream[, arg])
        _source, tree = _source_of(function)
        arity = len(tree.args.args) - 2
        if arity not in (0, 1):
            raise _Unsupported(
                f"{self.cls.__name__}.{self.method}: expected (self, stream[, arg])"
            )

        if len(tree.args.args) < 2 or tree.args.args[1].arg != "stream":
            raise _Unsupported(
                f"{self.cls.__name__}.{self.method}: second argument must be stream"
            )

        self.fn = self.compiler.new_function(
            self.path,
            self.method,
            arity,
            param=None if arity == 0 else tree.args.args[2].arg,
        )
        self.globals = function.__globals__

        if arity == 1:
            param_name = tree.args.args[2].arg
            self.vars[param_name] = self.fn.local(param_name)

        # process the function body
        try:
            body = tree.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]  # a docstring is not an instruction

            for stmt in body:
                self.stmt(stmt)

        except _Unsupported as err:
            raise UnsupportedNode(
                f"{self.cls.__name__}.{self.method}: {err}", self.path
            ) from None

        self.fn.ret(None if self.method == "read" else self.fn.const(0))
        self.fn.finish()

        return True

    # -- statements -------------------------------------------------------
    def result(self, value: int = 0):
        """
        A value for an expression whose result may be discarded.
        """
        return self.fn.const(value)

    def stmt(self, node: ast.AST):
        if isinstance(node, ast.Expr):
            # The value is discarded; a non-void call still has to happen.
            self.discard_result = True
            try:
                value = self.expr(node.value)
                if isinstance(value, nodes.Call):
                    self.fn.emit(nodes.CallStmt(None, value.func, value.arg))
            finally:
                self.discard_result = False
            return
        elif isinstance(node, ast.Assign):
            self.assign(node)
        elif isinstance(node, ast.AugAssign):
            self.augassign(node)
        elif isinstance(node, ast.If):
            self.if_(node)
        elif isinstance(node, ast.For):
            self.for_(node)
        elif isinstance(node, ast.While):
            self.while_(node)
        elif isinstance(node, ast.Return):
            if self.nb_depth:
                raise _Unsupported(
                    f"line {node.lineno}: return inside a counted region; "
                    "close the region before returning"
                )
            if node.value is None:
                value = None if self.method == "read" else self.fn.const(0)
            else:
                value = self.expr(node.value)
            self.fn.ret(value)
        elif isinstance(node, ast.With):
            self.with_(node)
        elif isinstance(node, ast.Assert):
            self.assert_stmt(node)
        elif isinstance(node, ast.Pass):
            self.fn.emit(nodes.Nop())
        else:
            raise _Unsupported(f"line {node.lineno}: statement {type(node).__name__}")

    def assign(self, node: ast.Assign):
        if len(node.targets) != 1:
            raise _Unsupported(f"line {node.lineno}: chained assignment")
        target = node.targets[0]

        if isinstance(target, ast.Name):
            value = self.expr(node.value)
            reg = self.var(target.id)
            if reg != value:
                self.fn.mov(reg, value)
            return

        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            if target.attr in self.state_fields:
                self.state_store(target.attr, node.value)
                return

            if isinstance(node.value, ast.Call) and _attr_name(node.value.func) == "append":
                self.buffer_append(target.attr, node.value)
                return

            raise _Unsupported(
                f"line {node.lineno}: assigning self.{target.attr}, which is not "
                "a State(); declare it as State(<default>) to make it a variable"
            )

        if _is_stream(node.targets[0], "cursor"):
            self.fn.set_cursor(self.expr(node.value))
            return

        raise _Unsupported(f"line {node.lineno}: assignment target")

    def buffer_append(self, attr: str, call: ast.Call):
        if len(call.args) != 1:
            raise _Unsupported("append expects one argument")

        buffer_id = self.compiler.buffer_id(self.path, attr)
        # Emit the generic operation: the detree-vm optimizer owns literal,
        # read/append, offset and length fusion.
        self.fn.buf_append(buffer_id, self.expr(call.args[0]))
        return self.result()

    def augassign(self, node: ast.AugAssign):
        op = BINARY_OPS.get(type(node.op))
        if op is None:
            raise _Unsupported(f"line {node.lineno}: operator {type(node.op).__name__}")

        if isinstance(node.target, ast.Name):
            target = self.var(node.target.id)
            self.fn.emit(op, rd=target, ra=target, rb=self.expr(node.value))
            return

        if (
            isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
            and node.target.attr in self.state_fields
        ):
            attr = node.target.attr
            if self.state_fields[attr].is_string:
                raise _Unsupported(f"line {node.lineno}: self.{attr} is a name")

            slot = self.compiler.state_id(self.path, attr)
            current = self.fn.state_get(slot)
            result = self.fn.reg()
            self.fn.emit(op, rd=result, ra=current, rb=self.expr(node.value))
            self.fn.state_set(slot, result)
            return

        raise _Unsupported(f"line {node.lineno}: augmented assignment target")

    def state_store(self, attr: str, value_node: ast.AST):
        slot = self.compiler.state_id(self.path, attr)
        register = self.expr(value_node)
        if self.state_fields[attr].is_string:
            self.fn.str_store(slot, register)
        else:
            self.fn.state_set(slot, register)

    def buffer_target(self, attr: str) -> tuple[int, Typecode]:
        """
        `(buffer id, machine typecode)` of a declared buffer of this reader.

        The reader declares a `struct` char; an instruction carries the
        numeric `Typecode`, so the lookup happens here, once.
        """
        buffer_id = self.compiler.buffer_id(self.path, attr)
        typecode = getattr(self.reader, attr).typecode
        try:
            return buffer_id, BUFFER_TYPECODES[typecode]
        except KeyError as err:
            raise _Unsupported(
                f"buffer {attr!r} has unsupported typecode {typecode!r}"
            ) from err

    def if_(self, node: ast.If):
        condition = self.condition_in(node.test)
        with self.fn.block() as then_block:
            for stmt in node.body:
                self.stmt(stmt)
        with self.fn.block() as else_block:
            for stmt in node.orelse:
                self.stmt(stmt)
        self.fn.if_(condition, then_block.statements, else_block.statements)

    def for_(self, node: ast.For):
        if not isinstance(node.target, ast.Name):
            raise _Unsupported(f"line {node.lineno}: for-loop target")
        call = node.iter
        if (
            isinstance(call, ast.Attribute)
            and isinstance(call.value, ast.Name)
            and call.value.id == "self"
            and call.attr in self.childlist_fields
        ):
            self.for_childlist(node, call.attr)
            return
        if not (isinstance(call, ast.Call) and _attr_name(call.func) == "range"):
            raise _Unsupported(f"line {node.lineno}: only range() loops are supported")
        if not 1 <= len(call.args) <= 2:
            raise _Unsupported(f"line {node.lineno}: range() with a step")

        if len(call.args) == 1:
            start = self.fn.const(0)
            stop = self.expr(call.args[0])
        else:
            start = self.expr(call.args[0])
            stop = self.expr(call.args[1])

        target = node.target.id
        saved = self.vars.get(target)
        self.vars[target] = self.fn.local(target)
        try:
            with self.fn.block() as block:
                for stmt in node.body:
                    self.stmt(stmt)
        finally:
            if saved is None:
                self.vars.pop(target, None)
            else:
                self.vars[target] = saved
        self.fn.for_range(target, start, stop, 1, block.statements)

    def for_childlist(self, node: ast.For, attr: str):
        """
        Unroll `for child in self.<childlist>:` over the declared childlist.

        A sub-reader is a different function, so the body is compiled once per
        child with the loop variable bound to that child's path.
        """
        if node.orelse:
            raise _Unsupported(f"line {node.lineno}: for/else")
        variable = node.target.id
        saved = self.loop_var
        try:
            for index, _ in enumerate(getattr(self.reader, attr)):
                self.loop_var = (variable, f"{self.path}/{attr}/{index}")
                for stmt in node.body:
                    self.stmt(stmt)
        finally:
            self.loop_var = saved

    def while_(self, node: ast.While):
        condition = self.condition_in(node.test)
        with self.fn.block() as block:
            for stmt in node.body:
                self.stmt(stmt)
        self.fn.while_(condition, block.statements)

    def condition_in(self, node: ast.AST):
        """
        Build a condition that is evaluated once per test.

        `check_nbytes_start()` opens a region with a statement, so it cannot
        appear inside a condition: the emitted statement would run before the
        branch or outside the loop, not where the source puts it.
        """
        saved = self.in_condition
        self.in_condition = True
        try:
            return self.condition(node)
        finally:
            self.in_condition = saved

    def assert_stmt(self, node: ast.Assert):
        self.fn.emit(
            nodes.Assert(self.expr(node.test), _assert_text(node, self.cls, self.method))
        )

    # -- counted regions ----------------------------------------------------
    def with_(self, node: ast.With):
        """
        Lower `with stream.check_nbytes():` to an `FNBEGIN`/`FNEND` pair.

        A counted region is machine state, so the pair is flat: the body is
        emitted between the two instructions and no cleanup path is needed.
        """
        if len(node.items) != 1:
            raise _Unsupported(f"line {node.lineno}: with takes one context")
        item = node.items[0]
        if item.optional_vars is not None:
            raise _Unsupported(f"line {node.lineno}: `with ... as` is not supported")
        if not _is_stream_call(item.context_expr, COUNTED_CONTEXT):
            raise _Unsupported(
                f"line {node.lineno}: only `with stream.{COUNTED_CONTEXT}():` is supported"
            )

        self.nb_start()
        for stmt in node.body:
            self.stmt(stmt)
        self.nb_end()

    def nb_start(self):
        """
        Open a counted region; the machine keeps the end position.
        """
        self.nb_depth += 1
        self.fn.emit(nodes.FNBegin())

    def nb_end(self, expected=None):
        """
        Close the innermost counted region, or check an explicit end.
        """
        if expected is None:
            if not self.nb_depth:
                raise _Unsupported(
                    "check_nbytes_end() with no open counted region; "
                    "call check_nbytes_start() first or pass the end position"
                )
            self.nb_depth -= 1
            self.fn.emit(nodes.FNEnd(self.nb_message()))
            return
        self.fn.assert_cursor_eq(expected, self.nb_message())

    def nb_message(self):
        """
        The message a failed frame check carries.

        The machine appends `(expected N, got M)` to it, so the text names the
        reader and method and nothing else.
        """
        return f"{self.cls.__name__}.{self.method}: the read did not end at the byte count"

    # -- conditions -------------------------------------------------------
    def _is_string_expr(self, value):
        if isinstance(value, nodes.StrConst):
            return True
        if isinstance(value, nodes.StateGet):
            return self.compiler.program.states[value.slot].type == "name"
        return isinstance(value, (nodes.StreamReadCString, nodes.RefGetClass))

    def compare(self, node: ast.Compare):
        operator = type(node.ops[0])
        left = self.expr(node.left)
        right = self.expr(node.comparators[0])
        if self._is_string_expr(left) or self._is_string_expr(right):
            if operator in (ast.Eq, ast.Is):
                return nodes.StrEq(left, right)
            if operator in (ast.NotEq, ast.IsNot):
                return nodes.Unary(Op.NOT_B, nodes.StrEq(left, right))
            raise _Unsupported(f"line {node.lineno}: string ordering")
        cmp = COMPARE_CMPS.get(operator)
        if cmp is None:
            raise _Unsupported(f"line {node.lineno}: comparison")
        return nodes.Compare(cmp, left, right)

    def condition(self, node: ast.AST):
        """
        Translate a condition to an IR expression.

        `and`/`or` become eager boolean arithmetic; reader conditions are
        pure comparisons, so evaluating both sides has no observable effect.
        The detree-vm optimizer owns any later folding.
        """
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return self.compare(node)
        if isinstance(node, ast.BoolOp):
            operator = Op.AND if isinstance(node.op, ast.And) else Op.OR
            values = list(node.values)
            result = self.condition(values[0])
            for value in values[1:]:
                result = nodes.Binary(operator, result, self.condition(value))
            return result
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            value = self.expr(node.operand)
            if self._is_string_expr(value):
                return nodes.StrEq(value, nodes.StrConst(self.compiler.constant("")))
            return nodes.Unary(Op.NOT_B, value)
        return self.expr(node)

    # -- expressions ------------------------------------------------------
    def expr(self, node: ast.AST):
        if isinstance(node, ast.Constant):
            if node.value is None:
                # A name slot that holds nothing; see native.State.
                return self.fn.const(-1)
            if isinstance(node.value, bool):
                return self.fn.const(int(node.value))
            if isinstance(node.value, int):
                return self.fn.const(node.value)
            if isinstance(node.value, str):
                return self.fn.str_const(self.compiler.constant(node.value))
            raise _Unsupported(f"line {node.lineno}: constant {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id in self.vars:
                return self.vars[node.id]
            value = self._module_constant(node.id)
            if value is not None:
                return self.fn.const(value)
            raise _Unsupported(f"line {node.lineno}: unknown name {node.id!r}")

        if isinstance(node, ast.Attribute):
            return self.attribute(node)

        if isinstance(node, ast.BinOp):
            op = BINARY_OPS.get(type(node.op))
            if op is None:
                raise _Unsupported(f"line {node.lineno}: operator {type(node.op).__name__}")
            return nodes.Binary(op, self.expr(node.left), self.expr(node.right))

        if isinstance(node, ast.UnaryOp):
            value = self.expr(node.operand)
            if isinstance(node.op, ast.USub):
                return nodes.Unary(Op.NEG, value)
            if isinstance(node.op, ast.Not):
                return nodes.Unary(Op.NOT_B, value)
            if isinstance(node.op, ast.Invert):
                return nodes.Unary(Op.NOT, value)
            raise _Unsupported(f"line {node.lineno}: unary {type(node.op).__name__}")

        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return self.compare(node)

        if isinstance(node, ast.Subscript):
            if _is_subscript_last(node, "self"):
                attr = node.value.attr
                return self.fn.buf_last(self.compiler.buffer_id(self.path, attr))
            raise _Unsupported(f"line {node.lineno}: subscript")

        if isinstance(node, ast.Call):
            return self.call(node)

        if isinstance(node, ast.IfExp):
            return self.ifexp(node)

        raise _Unsupported(f"line {node.lineno}: expression {type(node).__name__}")

    def attribute(self, node: ast.Attribute):
        if not isinstance(node.value, ast.Name):
            raise _Unsupported(f"line {node.lineno}: attribute chain")
        base, attr = node.value.id, node.attr

        if base == "stream":
            if attr == "cursor":
                return self.fn.cursor()
            if attr == "entries":
                return self.fn.entries()
            if attr == "initial_cursor_position":
                return self.fn.init_offset()
            raise _Unsupported(f"line {node.lineno}: stream.{attr}")

        if base == "self":
            if attr in self.state_fields:
                slot = self.compiler.state_id(self.path, attr)
                if self.state_fields[attr].is_string:
                    return self.fn.str_load(slot)
                return self.fn.state_get(slot)
            if attr in self.const_fields:
                value = getattr(self.reader, attr)
                if isinstance(value, bool):
                    return self.fn.const(int(value))
                if isinstance(value, int):
                    return self.fn.const(value)
                if isinstance(value, str):
                    return self.fn.str_const(self.compiler.constant(value))
                raise _Unsupported(
                    f"line {node.lineno}: Const({attr}) is {value!r}, "
                    "which has no bytecode constant"
                )
            raise _Unsupported(
                f"line {node.lineno}: self.{attr} is not a field, so the compiled "
                "read path cannot see it; declare it with Const() if read() needs it"
            )

        raise _Unsupported(f"line {node.lineno}: attribute {base}.{attr}")

    def call(self, node: ast.Call):
        func = node.func

        if isinstance(func, ast.Attribute):
            owner = func.value
            if isinstance(owner, ast.Name):
                if self.loop_var is not None and owner.id == self.loop_var[0]:
                    return self.child_call_at(self.loop_var[1], func.attr, node)
                if owner.id == "stream":
                    return self.stream_call(func.attr, node)
                if owner.id == "self":
                    attr = func.attr
                    value = getattr(self.reader, attr, None)
                    if callable(value) and not _is_reader(value):
                        return self.helper_call(attr, node)
                    raise _Unsupported(f"line {node.lineno}: self.{attr}() is not a method")
                raise _Unsupported(f"line {node.lineno}: call on {owner.id!r}")
            if (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "self"
            ):
                value = getattr(self.reader, owner.attr, None)
                if isinstance(value, BufferProxy) and func.attr == "append":
                    return self.buffer_append(owner.attr, node)
                return self.child_call(owner.attr, func.attr, node)
            raise _Unsupported(f"line {node.lineno}: call target")

        if isinstance(func, ast.Name):
            if func.id in ("bool", "int"):
                if len(node.args) != 1:
                    raise _Unsupported(f"line {node.lineno}: {func.id}() arity")
                value = self.expr(node.args[0])
                if func.id == "int":
                    return value
                inverted = self.fn.reg()
                self.fn.emit(Op.NOT_B, rd=inverted, ra=value)
                twice = self.fn.reg()
                self.fn.emit(Op.NOT_B, rd=twice, ra=inverted)
                return twice
            if func.id == "len":
                arg = node.args[0]
                if _self_buffer(arg) is not None:
                    return self.fn.buf_len(self.compiler.buffer_id(self.path, arg.attr))
                raise _Unsupported(f"line {node.lineno}: len() of a non-buffer")
            raise _Unsupported(f"line {node.lineno}: builtin {func.id}()")

        raise _Unsupported(f"line {node.lineno}: call")

    def stream_call(self, name: str, node: ast.Call):
        if name in STREAM_READS:
            if node.args:
                raise _Unsupported(f"line {node.lineno}: {name} takes no arguments")
            return self.fn.read_scalar(STREAM_READS[name])
        if name == "read_fNBytes":
            return self.fn.read_fnb()
        if name == "check_nbytes_start":
            if node.args or node.keywords:
                raise _Unsupported(
                    f"line {node.lineno}: check_nbytes_start takes no arguments"
                )
            if self.in_condition:
                raise _Unsupported(
                    f"line {node.lineno}: check_nbytes_start() cannot be used in a condition"
                )
            self.nb_start()
            return self.result()
        if name == "check_nbytes_end":
            if node.keywords:
                raise _Unsupported(f"line {node.lineno}: keyword arguments")
            if len(node.args) > 1:
                raise _Unsupported(
                    f"line {node.lineno}: check_nbytes_end takes at most one argument"
                )
            expected = self.expr(node.args[0]) if node.args else None
            self.nb_end(expected)
            return self.result()
        if name == "read_fVersion":
            return self.fn.read_version()
        if name == "read_null_terminated_string":
            return self.fn.read_cstr()
        if name in STREAM_SKIPS:
            self.fn.emit(STREAM_SKIPS[name])
            return self.result()
        if name == "skip":
            if not node.args:
                raise _Unsupported("skip() needs a size")
            size = node.args[0]
            if (
                isinstance(size, ast.Constant)
                and isinstance(size.value, int)
                and not isinstance(size.value, bool)
                and size.value >= 0
            ):
                # `stream.skip(2)` is one SKIP, not a CONST plus SKIP_R.
                self.fn.skip(size.value)
            else:
                self.fn.skip_reg(self.expr(size))
            return self.result()
        if name in ("read_into", "read_bulk"):
            attr = _require_self_buffer(node.args[0])
            buffer_id, typecode = self.buffer_target(attr)
            if name == "read_into":
                self.fn.emit(Op.READ_APPEND, imm1=buffer_id, imm2=int(typecode))
            else:
                self.fn.read_bulk(buffer_id, typecode, self.expr(node.args[1]))
            return self.result()
        if name == "next_offset_after":
            return self.fn.offset_seek(self.expr(node.args[0]))
        if name == "has_ref":
            return self.fn.ref_has(self.expr(node.args[0]))
        if name == "ref_object_index":
            return self.fn.ref_get_obj(self.expr(node.args[0]))
        if name == "ref_class_name":
            return self.fn.ref_get_class(self.expr(node.args[0]))
        if name == "ref_count":
            return self.fn.ref_count()
        if name == "set_object_ref":
            self.fn.ref_set_obj(self.expr(node.args[0]), self.expr(node.args[1]))
            return self.result()
        if name == "set_class_ref":
            self.fn.ref_set_class(self.expr(node.args[0]), self.expr(node.args[1]))
            return self.result()
        if name == "check_class_name":
            left = self.expr(node.args[0])
            right = self.expr(node.args[1])
            message = f"{self.cls.__name__}.{self.method}: inconsistent class names"
            self.fn.assert_str_eq(left, right, message)
            return self.result()
        raise _Unsupported(f"line {node.lineno}: stream.{name}()")

    def helper_call(self, name: str, node: ast.Call):
        if node.keywords:
            raise _Unsupported(f"line {node.lineno}: keyword arguments")
        if not node.args:
            raise _Unsupported(f"line {node.lineno}: helper without a stream")
        arity = len(node.args) - 1
        if arity > 1:
            raise _Unsupported(f"line {node.lineno}: helper with two arguments")
        if name in ENTRY_METHODS:
            function_id = self.compiler.func_id(self.path, name)
        else:
            if not hasattr(type(self.reader), name):
                raise _Unsupported(
                    f"line {node.lineno}: self.{name} is not a method of the reader"
                )
            compile_method(self.compiler, self.reader, self.path, name)
            function_id = self.compiler.func_id(self.path, name)
        argument = None if arity == 0 else self.expr(node.args[1])
        return self.fn.call(function_id, argument)

    def child_call(self, attr: str, method: str, node: ast.Call):
        child = getattr(self.reader, attr, None)
        if not _is_reader(child):
            raise _Unsupported(f"line {node.lineno}: self.{attr} is not a reader")
        return self.child_call_at(f"{self.path}/{attr}", method, node)

    def child_call_at(self, child_path: str, method: str, node: ast.Call):
        if method not in ENTRY_METHODS:
            raise _Unsupported(f"line {node.lineno}: child method {method}")
        if len(node.args) < 1:
            raise _Unsupported(f"line {node.lineno}: child call without a stream")
        argument = None
        if len(node.args) > 1:
            argument = self.expr(node.args[1])
        return self.fn.call(self.compiler.func_id(child_path, method), argument)

    def _compile_helper(self, name: str):
        compile_method(self.compiler, self.reader, self.path, name)

    def ifexp(self, node: ast.IfExp):
        target = self.fn.temp()
        condition = self.condition(node.test)
        with self.fn.block() as then_block:
            self.fn.emit(nodes.Assign(target, self.expr(node.body)))
        with self.fn.block() as else_block:
            self.fn.emit(nodes.Assign(target, self.expr(node.orelse)))
        self.fn.if_(condition, then_block.statements, else_block.statements)
        return target

    def var(self, name: str):
        reg = self.vars.get(name)
        if reg is None:
            reg = self.fn.local(name)
            self.vars[name] = reg
        return reg

    def _module_constant(self, name: str):
        """
        An `int`/`bool` module-level constant, such as `kByteCountMask`.
        """
        value = getattr(self, "globals", {}).get(name)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        return None


def _attr_name(func):
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_stream(node, attribute) -> bool:
    """
    Check if the given node represents an attribute access on the 'stream'
    object with the specified attribute name.
    """
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "stream"
        and node.attr == attribute
    )


def _self_buffer(node):
    """
    `self.<attr>` as a buffer attribute name, or `None`.
    """
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _require_self_buffer(node):
    attr = _self_buffer(node)
    if attr is None:
        raise _Unsupported("a buffer argument must be self.<buffer>")
    return attr


def _is_stream_call(node, name: str) -> bool:
    """
    Whether *node* is `stream.<name>()` with no arguments.

    The lint in `decl` accepts the same shape, so a `with` that reaches the
    compiler is always the counted region; the check here is the second line
    of defence.
    """
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "stream"
        and node.func.attr == name
        and not node.args
        and not node.keywords
    )


def _is_subscript_last(node, owner, attribute=None):
    if not isinstance(node, ast.Subscript):
        return False
    if not isinstance(node.value, ast.Attribute):
        return False
    if not isinstance(node.value.value, ast.Name) or node.value.value.id != owner:
        return False
    if attribute is not None and node.value.attr != attribute:
        return False
    index = node.slice
    return isinstance(index, ast.UnaryOp) and isinstance(index.op, ast.USub)


def _assert_text(node, cls, method):
    message = node.msg
    if isinstance(message, ast.Constant) and isinstance(message.value, str):
        return message.value
    return f"{cls.__name__}.{method}: assertion failed"


def compile_method(compiler: _Compiler, reader: Reader, path: str, method: str):
    """
    Compile one method of *reader*; return its function id.
    """
    key = (path, method)
    if key in compiler.compiled:
        return compiler.func_id(path, method)
    if getattr(type(reader), method) is getattr(Reader, method, None):
        raise _Unsupported(f"{method} is not overridden")
    compiler.compiled.add(key)
    _MethodEmitter(compiler, reader, path, method).emit()
    return compiler.func_id(path, method)


def _emit_defaults(compiler: _Compiler, reader: Reader, path: str):
    """
    Fill in the entry points the class does not override.
    """
    for method in ("read_many", "read_until", "read_many_memberwise"):
        slot = compiler.slot_by_key[(path, method)]
        if slot.function.body:
            continue

        fn = compiler.new_function(path, method, 1)
        read_id = compiler.func_id(path, "read")

        if method == "read_many_memberwise":
            fn.throw(f"{path}: read_many_memberwise is not implemented")
            fn.ret(fn.const(0))
            continue

        if method == "read_many":
            count = fn.local("count")
            fn.for_range(
                "__i",
                fn.const(0),
                count,
                1,
                [nodes.CallStmt(None, read_id, None)],
            )
            fn.ret(count)
            continue

        end_pos = fn.local("end_pos")
        count = fn.local("__count")
        fn.emit(nodes.Assign(count, fn.const(0)))
        fn.while_(
            nodes.Compare(Op.CMP_LT_S, nodes.Cursor(), end_pos),
            [
                nodes.CallStmt(None, read_id, None),
                nodes.Assign(count, nodes.Binary(Op.ADD, count, fn.const(1))),
            ],
        )
        fn.ret(count)


def compile_reader(reader):
    """
    Compile a whole reader tree; return `(module bytes, signature)`.

    Args:
        reader: the root of the detree reader tree.

    Returns:
        The canonical module bytes and the structural signature they were
        built from.
    """
    if not isinstance(reader, Reader):
        raise UnsupportedNode(
            f"{type(reader).__name__} is not a detree reader; the detree backend "
            "only compiles classes built on uproot_custom.detree.decl.Reader"
        )
    for path, node in _walk(reader):
        if not type(node).__dict__.get("__reader_checked__", False):
            raise UnsupportedNode(
                f"{type(node).__name__} must be decorated with @reader", path
            )

    compiler = _Compiler(reader)
    for path, node in _walk(reader):
        compile_method(compiler, node, path, "read")
        for method in ("read_many", "read_until", "read_many_memberwise"):
            if getattr(type(node), method) is not getattr(Reader, method):
                compile_method(compiler, node, path, method)
        _emit_defaults(compiler, node, path)
    codes = compiler.build()

    if os.environ.get("UPROOT_CUSTOM_DETREE_DUMP_MODULES") or os.environ.get(
        "UPROOT_CUSTOM_JIT_DUMP_MODULES"
    ):
        from detree.spec.module import Module as IRModule

        for i, ins in enumerate(IRModule.from_bytes(codes).code):
            print(f"{i:04}: {ins}")

    return codes, describe_reader(reader)


def _walk(reader, path="root"):
    yield path, reader
    for _, child, suffix in _reader_children(reader):
        yield from _walk(child, path + suffix)


__all__ = [
    "compile_reader",
    "describe_reader",
]
