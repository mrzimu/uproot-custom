from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Literal

import numpy as np

from uproot_custom.consts import _MISSING, DTYPE_TO_TYPECODE, TYPECODE
from uproot_custom.detree.bufferproxy import BufferProxy
from uproot_custom.detree.stream import Stream


# -- Fields ----------------------------------------------------------------------
class ReaderContractError(TypeError):
    """
    A reader class violates the contract `reader` enforces.
    """


class _Field:
    def __init__(self):
        self.name: str = None

    def bind(self, name: str, owner):
        if name.startswith("_"):
            raise ReaderContractError(
                f"{owner.__name__}.{name}: field names cannot start with an underscore"
            )
        self.name = name


class Const(_Field):
    _allowed_types = (bool, int, str)

    def __init__(
        self,
        default=_MISSING,
        *,
        type=None,
        choices=None,
        ge=None,
        le=None,
    ):
        if type is not None and type not in self._allowed_types:
            raise TypeError(
                f"Const's type can only be {', '.join(t.__name__ for t in self._allowed_types)}; "
                f"got {type.__name__}"
            )

        if default is not _MISSING:
            if type is not None:
                if not isinstance(default, type):
                    raise ValueError(f"Value {default} is not of type {type.__name__}")
            else:
                if not isinstance(default, self._allowed_types):
                    raise ValueError(
                        f"Value {default} is not of an allowed type {', '.join(t.__name__ for t in self._allowed_types)}"
                    )

        self.default = default
        self.type = type
        self.choices = None if choices is None else tuple(choices)
        self.ge = ge
        self.le = le

    def coerce(self, name: str, value):
        """
        Coerce the given value to the expected type, and check its bounds.
        """
        if value is _MISSING:
            if self.default is _MISSING:
                raise TypeError(f"{name}: missing required argument")
            value = self.default

        expected = self.type
        if expected is None and self.default is not _MISSING:
            expected = type(self.default)

        if expected is bool:
            if not isinstance(value, (bool, np.bool_)):
                raise TypeError(f"{name}: expected bool, got {value!r}")
            value = bool(value)
        elif expected is int:
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise TypeError(f"{name}: expected int, got {value!r}")
            value = int(value)
        elif expected is str:
            if not isinstance(value, str):
                raise TypeError(f"{name}: expected str, got {value!r}")
        elif expected is not None and not isinstance(value, expected):
            raise TypeError(f"{name}: expected {expected.__name__}, got {value!r}")

        if self.choices is not None and value not in self.choices:
            raise ValueError(f"{name}: {value!r} not in {sorted(self.choices)!r}")
        if self.ge is not None and value < self.ge:
            raise ValueError(f"{name}: {value!r} < {self.ge}")
        if self.le is not None and value > self.le:
            raise ValueError(f"{name}: {value!r} > {self.le}")

        return value


#: fixed-width typecodes ``array.array`` and the machine agree on.  ``l``/``L``
#: are platform-dependent (8 bytes on Linux) and have no coercer in the VM, so a
#: buffer may not be declared with them.
_BUFFER_TYPECODES = ("b", "B", "h", "H", "i", "I", "q", "Q", "f", "d")


def _check_typecode(typecode):
    if typecode not in _BUFFER_TYPECODES:
        raise TypeError(
            f"Buffer: unsupported typecode {typecode!r}; "
            f"use one of {', '.join(_BUFFER_TYPECODES)}"
        )
    return typecode


def _to_typecode(value):
    """
    Normalise a buffer's element type to a fixed-width typecode.

    Accepts a typecode (``"i"``), a NumPy dtype (``np.int32``,
    ``np.dtype("i4")``) or a dtype string (``"int32"``, ``"<i4"``).  A dtype
    name is looked up by its normalised name, so byte order and aliases do not
    matter; only the fixed-width dtypes the machine can read are accepted.
    """
    if isinstance(value, str):
        if value in _BUFFER_TYPECODES:
            return value
        if value in ("l", "L"):
            # A single letter reads as a typecode first; ``l``/``L`` are the
            # platform-dependent codes the machine has no coercer for.
            raise TypeError(
                f"Buffer: unsupported typecode {value!r}; "
                f"use one of {', '.join(_BUFFER_TYPECODES)}"
            )

    try:
        name = np.dtype(value).name
    except (TypeError, ValueError):
        raise TypeError(f"Buffer: {value!r} is not a typecode or a NumPy dtype") from None

    if name not in DTYPE_TO_TYPECODE:
        raise TypeError(
            f"Buffer: unsupported dtype {value!r}; "
            f"use one of {', '.join(sorted(DTYPE_TO_TYPECODE))}"
        )
    return DTYPE_TO_TYPECODE[name]


class Buffer(_Field):
    """
    A typed buffer that a read path appends to.

    The element type is a ``struct`` typecode (``"i"``), a NumPy dtype
    (``np.int32``, ``np.dtype("i4")``) or a dtype string (``"int32"``); all
    forms normalise to the fixed-width typecode the machine stores.
    """

    def __init__(
        self,
        type: TYPECODE | np.dtype | type | str | None = None,
        *,
        init=(),
        from_const: str | None = None,
        kind: Literal["data", "offsets"] = "data",
    ):
        if type is None and from_const is None:
            raise TypeError("Buffer: pass a type or name a Const field in from_const")
        if kind not in ("data", "offsets"):
            raise TypeError("Buffer: kind must be 'data' or 'offsets'")

        self.typecode = None if type is None else _to_typecode(type)
        self.init = tuple(init)
        self.from_const = from_const
        self.kind = kind

    def resolve_typecode(self, reader) -> TYPECODE:
        """
        The normalised typecode of this buffer in *reader*, after its
        constants are set.

        A reader whose element type is a constructor argument (a primitive, a
        `TArray`) names that `Const` field in `from_const`, so one class
        serves every dtype.  The constant has to be declared *before* the
        buffer, which is also the order the fields are initialised in.
        """
        if self.from_const is None:
            return self.typecode
        return _check_typecode(getattr(reader, self.from_const))


class State(_Field):
    _allowed_types = (bool, int, str)

    def __init__(self, type, init=None):
        if type not in self._allowed_types:
            raise TypeError(
                f"State's type can only be {', '.join(t.__name__ for t in self._allowed_types)}; "
                f"got {type.__name__}"
            )

        self.type = type
        self.init = init

    @property
    def is_string(self):
        return self.type is str


class Child(_Field):
    """
    Standalone child field.
    """


class ChildList(_Field):
    """
    List of child fields.
    """


# TODO: Implement ChildDict functionality when needed
class ChildDict(_Field):
    """
    Dictionary of child fields, not enabled yet.
    """


# -- Reader ----------------------------------------------------------------------
class Reader:
    __fields__: tuple[_Field, ...] = ()
    __jit_checked__ = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # fetch the closest ancestor's fields
        inherited: tuple[_Field, ...] = ()
        for base in cls.__mro__[1:]:
            if issubclass(base, Reader) and base is not Reader:
                inherited = base.__fields__
                break
        inherited_names = {f.name for f in inherited}

        # collect all _Field instances declared in this subclass
        declared: list[_Field] = []
        for name, value in list(vars(cls).items()):
            if isinstance(value, _Field):
                if name in inherited_names:
                    raise ReaderContractError(
                        f"{cls.__name__}.{name}: cannot override inherited field"
                    )
                value.bind(name, cls)
                declared.append(value)
                delattr(cls, name)

        # combine ancestor's fields with the declared fields, override any with the same name
        names = {f.name for f in declared} | inherited_names
        fields = tuple([f for f in inherited if f.name not in names] + declared)

        for bad in ("read", "data", "read_many", "read_until", "read_many_memberwise"):
            if bad in names:
                raise ReaderContractError(
                    f"{cls.__name__}.{bad}: a field cannot share the name of a method"
                )

        cls.__fields__ = fields

    def __init__(self, name: str, **values):
        self.name = name

        for field in self.__fields__:
            raw = values.pop(field.name, _MISSING)

            if isinstance(field, Const):
                value = field.coerce(field.name, raw)

            elif isinstance(field, State):
                value = field.init if raw is _MISSING else raw
                if value is not None and not isinstance(value, field.type):
                    raise TypeError(
                        f"{field.name}: expected {field.type.__name__} or None, got {value!r}"
                    )

            elif isinstance(field, Buffer):
                value = BufferProxy(field.resolve_typecode(self), field.init, kind=field.kind)

            elif isinstance(field, Child):
                if not isinstance(raw, Reader):
                    raise TypeError(f"{field.name}: expected a Reader, got {raw!r}")
                value = raw

            elif isinstance(field, ChildList):
                if raw is _MISSING:
                    raw = ()
                if not isinstance(raw, (tuple, list)):
                    raise TypeError(f"{field.name}: expected a tuple or list of Reader")
                value = tuple(raw)
                for item in value:
                    if not isinstance(item, Reader):
                        raise TypeError(f"{field.name}: expected a Reader, got {item!r}")
            else:
                raise TypeError(
                    f"{field.name}: field type {type(field).__name__} is not supported yet"
                )

            setattr(self, field.name, value)

        if values:
            raise TypeError(f"{type(self).__name__}: unexpected argument {min(values)!r}")

    def read(self, stream: Stream):
        raise NotImplementedError("read method must be implemented by subclasses")

    def read_many(self, stream: Stream, count: int):
        for _ in range(count):
            self.read(stream)
        return count

    def read_until(self, stream: Stream, end_pos: int):
        count = 0
        while stream.cursor < end_pos:
            self.read(stream)
            count += 1
        return count

    def read_many_memberwise(self, stream: Stream, count: int):
        raise NotImplementedError(f"{type(self).__name__}.read_many_memberwise")

    def data(self):
        raise NotImplementedError("data method must be implemented by subclasses")

    def reset(self):
        for field in self.__fields__:
            if isinstance(field, Buffer):
                getattr(self, field.name).reset()
            elif isinstance(field, State):
                setattr(self, field.name, field.init)

        for child in self.children:
            child.reset()

    @property
    def buffers(self):
        return tuple(
            getattr(self, field.name) for field in self.__fields__ if isinstance(field, Buffer)
        )

    @property
    def children(self):
        result: list[Reader] = []
        for field in self.__fields__:
            if isinstance(field, Child):
                result.append(getattr(self, field.name))
            elif isinstance(field, ChildList):
                result.extend(getattr(self, field.name))
        return tuple(result)

    def __repr__(self):
        return f"<{type(self).__name__} {self.name!r}>"


# -- the decorator --------------------------------------------------------
_ALLOWED_ARITY = {"read": 2, "read_many": 3, "read_until": 3, "read_many_memberwise": 3}

# statement and expression nodes a read path may contain
_BANNED_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Lambda,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.AsyncFor,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Delete,
    ast.Raise,
    ast.Dict,
    ast.Set,
    ast.Starred,
)


def _holds_undecl_readers(value):
    if isinstance(value, (tuple, list)):
        return any(isinstance(item, Reader) for item in value)
    if isinstance(value, dict):
        return any(isinstance(item, Reader) for item in value.values())
    return False


def _check_signature(cls, method, function, arity):
    tree = _parse(cls, method, function)
    args = tree.args.args
    if len(args) != arity:
        raise ReaderContractError(
            f"{cls.__name__}.{method}: expected (self, stream"
            f"{', argument' if arity == 3 else ''})"
        )
    if args[1].arg != "stream":
        raise ReaderContractError(
            f"{cls.__name__}.{method}: second argument must be named stream"
        )


def _parse(cls, method, function):
    tree = _parse_source(function)
    if tree is None:
        raise ReaderContractError(
            f"{cls.__name__}.{method}: source is not available; "
            "readers must live in a .py file"
        )
    return tree


def _parse_source(function):
    try:
        source = textwrap.dedent(inspect.getsource(function))
    except (OSError, TypeError):
        return None
    tree = ast.parse(source)
    if not tree.body or not isinstance(tree.body[0], ast.FunctionDef):
        return None
    return tree.body[0]


def _lint(cls, method, function):
    tree = _parse_source(function)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, _BANNED_NODES):
            raise ReaderContractError(
                f"{cls.__name__}.{method}: line {node.lineno}: "
                f"{type(node).__name__} cannot be compiled"
            )


def _assigned_self_names(tree):
    """
    Names assigned through `self.<name>` anywhere in *tree*.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                names.add(target.attr)
    return names


def _check_assignments(cls, method, function):
    """
    A read path may only assign to a declared `State`.

    This is the one rule about members that a Python-side check can enforce
    usefully: `self.x = ...` needs a place to live in the machine, and only a
    state slot is one.  A plain class attribute is fine everywhere else -- it is
    simply not visible to the compiled code.
    """
    tree = _parse_source(function)
    if tree is None:
        return
    states = {f.name for f in cls.__fields__ if isinstance(f, State)}
    for assigned in _assigned_self_names(tree):
        if assigned in states:
            continue
        raise ReaderContractError(
            f"{cls.__name__}.{method}: self.{assigned} is assigned, so it has to "
            "be a variable -- declare it as State(<default>); a plain attribute "
            "or a Const() cannot be written in a read path"
        )


def reader(cls):
    """
    Class decorator enforcing the reader contract.
    """
    if not isinstance(cls, type) or not issubclass(cls, Reader):
        raise TypeError(f"@reader expects a Reader subclass, got {cls!r}")

    if "__init__" in cls.__dict__:
        raise ReaderContractError(
            f"{cls.__name__}: do not override __init__; declare fields instead"
        )

    if cls.read is Reader.read:
        raise ReaderContractError(f"{cls.__name__}: a reader must define read()")

    if cls.data is Reader.data:
        raise ReaderContractError(f"{cls.__name__}: a reader must define data()")

    for name, value in vars(cls).items():
        if name.startswith("__") and name.endswith("__"):
            continue

        if isinstance(value, Reader) or _holds_undecl_readers(value):
            raise ReaderContractError(
                f"{cls.__name__}.{name}: a sub-reader is a field, not a class "
                "attribute; declare it with Child() or ChildList()"
            )

    for method, arity in _ALLOWED_ARITY.items():
        function = cls.__dict__.get(method)
        if function is None:
            continue
        _check_signature(cls, method, function, arity)
        _lint(cls, method, function)
        _check_assignments(cls, method, function)

    cls.__jit_checked__ = True

    return cls
