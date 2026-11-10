# Detree reader reference

This page is the reference for the Detree reader DSL and the compiler that consumes it. It lists every field, the contract a reader must satisfy, the Python subset the compiler accepts, and what the backend does at run time.

For the guided version, read [Write a Detree reader](../tutorial/write-a-reader.md).

## Status

```{important}
The Detree route is **experimental**. It is the recommended way for a downstream project to add its own readers, and every built-in factory implements it, but the DSL may still change between minor releases.

Detree-VM's official release ships the **Rust** machine only. The Python and C++ machines are development references and are not selectable through the public API.
```

```{note}
A Detree reader is written in Python but never runs as Python: the compiler turns it into module bytes. Two other things are also "Python" and are not this one — Detree's Python executor (`uproot_custom.detree.interp`), which runs a Detree reader's methods for debugging, and the `python` backend, which executes a separate `IReader` implementation. See [choosing a technical route](../concepts/choosing-a-route.md#three-things-called-python).
```

## Declaring a reader

A Detree reader is a class decorated with `@reader` that inherits from `Reader`:

```python
import numpy as np

from uproot_custom.detree import Buffer, Reader, reader


@reader
class IntListReader(Reader):
    """
    A `uint32` count followed by that many `int32` values.
    """

    # kind="offsets" allows compiler to optimize offset calculations
    offsets = Buffer("q", init=(0,), kind="offsets")
    values = Buffer("i")

    def read(self, stream):
        count = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + count)
        for _ in range(count):
            self.values.append(stream.read_int32())

    def data(self):
        return np.asarray(self.offsets), np.asarray(self.values)
```

`read` is compiled and runs inside the machine. `data` is ordinary Python that runs on the filled buffers, so keep it consistent with your factory's `make_awkward_content` — the same requirement as for a Python or C++ reader.

### Fields

| Field | Purpose |
| ----- | ------- |
| `Const(default, type=..., choices=..., ge=..., le=...)` | a constructor argument fixed for the branch; readable in `read`, never writable |
| `Buffer(type, *, init=(), from_const=None, kind="data")` | a typed output array. `type` is a `struct` typecode (`"i"`), a NumPy dtype (`np.int32`) or a dtype string (`"int32"`), and it is positional — `Buffer(typecode=...)` is not a keyword. `kind="offsets"` marks a buffer of cumulative offsets that begins at `init`. `from_const` takes the typecode from a `Const` field, which is how one class serves every dtype |
| `State(type, init)` | a variable that survives the entries of one basket and returns to `init` when the reader is rebuilt for the next basket; the only kind of attribute a read path may assign. A `State(str, ...)` holds a name slot: a `str` in Python, a string-arena id in the machine, `-1` for none |
| `Child()` | exactly one sub-reader |
| `ChildList()` | an ordered tuple of sub-readers; a `for` loop over it is unrolled |

### The reader contract

The `@reader` decorator checks the following at class definition time:

- the class is defined in a `.py` file — the compiler re-reads its source, so a class typed into a notebook or a REPL is refused;
- no `__init__`; declare fields instead and pass values as keyword arguments, e.g. `TArrayReader(name, typecode="d")` for a reader whose `typecode` is a `Const` field;
- `read(self, stream)` and `data(self)` are required; `read_many`, `read_until`, and `read_many_memberwise` take `(self, stream, argument)` and default to loops over `read`, except `read_many_memberwise` (see below);
- the second parameter is named `stream`;
- field names do not start with `_`, are not inherited and overridden, and do not collide with the method names;
- a read path assigns only to declared `State` fields (or `stream.cursor`); a plain attribute is invisible to the compiled code, and a `Const` cannot be written.

Implement `read_many_memberwise` when the reader can appear in a memberwise-stored container (an element of `vector<T>`, or a key or value of `map<K, V>`). The default one throws at run time rather than silently reading the wrong bytes.

## The compilable subset

`read`, `read_many`, `read_until`, and `read_many_memberwise` are compiled from source, so they must stay within a small subset of Python:

| Allowed | What |
| ------- | ---- |
| statements | `if`/`else`, `while`, `for _ in range(n)`, `for child in self.<ChildList>`, `assert`, `pass`, assignment to a local, a `State`, or `stream.cursor` |
| integer and boolean expressions | `+ - * // / % << >> & \| ^ ~`, unary `-`, comparisons, `if` expression, `and`/`or`/`not` in conditions, `bool()`, `int()` |
| buffers | `buf.append(x)`, `len(buf)`, `buf[-1]` |
| stream | the scalar `read_*` methods, `read_into`, `read_bulk`, `read_fNBytes`, `read_fVersion`, `read_null_terminated_string`, `skip` and the `skip_*` helpers, `next_offset_after`, `cursor`, `entries`, `initial_cursor_position`, `has_ref`, `ref_*`, `set_*_ref`, `check_class_name` |
| names | module-level `int` and `bool` constants, e.g. `kByteCountMask` |

| Not allowed | Reason |
| ----------- | ------ |
| imports, `try`, `with`, `raise`, `del`, `global`, `lambda`, comprehensions, generators | no bytecode for them; report a bad record with `assert` instead of `raise` |
| dict, set, or list literals, starred expressions | ditto |
| `print`, numpy, `isinstance`, `getattr`, calls into arbitrary functions or stored bound methods | run outside the machine |
| `self.<attr>` where `attr` is not a declared field | invisible to the compiled code |
| chained assignment; `for` over anything but `range()` or a declared `ChildList` | not compiled |
| string ordering (`<`, `>`) | only `==` and `!=` on names |
| buffer typecodes `l` and `L` | platform-dependent; use a fixed-width code |

A construct outside the subset fails with `ReaderContractError` (when the class is defined) or `UnsupportedNode` (when the reader is compiled), naming the method and the offending line. Rewrite the reader, or take the [Python + C++ route](../advanced/index.md); there is no fallback for a reader the compiler rejects.

## How compilation works

```{mermaid}
flowchart TB
    F["Factory"] --> R["detree reader tree"]
    R --> C["compile_reader"]
    C --> M["Detree module"]
    M --> VM["Detree machine"]
    VM --> B["buffers and state"]
    B --> D["Reader.data()"]
    D --> A["awkward content"]
```

Every backend shares the same `Factory`: it decides which reader to build and how the raw data becomes an awkward array. Only the byte-level reader differs, so a branch decodes to the same array on every backend.

The reader is *declarative*. It declares its output buffers, per-basket state, constants, and sub-readers as fields; its `read` method is ordinary Python source that the compiler turns into bytecode. Nothing in `read` runs as Python during a read — `data` does, once per basket, to turn the filled buffers into the tuple, list, or arrays your factory consumes.

## Limitations

### A branch is compiled or it is not

There is no fallback to another backend. When a factory cannot build a Detree reader, the first read raises

```{code-block} console
NotImplementedError: <Factory> does not implement build_detree_reader; use a
different reader backend
```

The failure is deliberate: a silent switch would make a benchmark, or a bug report, describe a machine that never ran. Select another backend for that read instead.

Note that the failure happens on the first read, not when the file is opened: the interpretation and its awkward form are built before the factory is asked for a reader.

### Awkward arrays only

All reader backends decode through `AsCustom`, which requires the awkward library. Reading with `library="np"` or `library="pd"` raises

```{code-block} console
AssertionError: Only awkward arrays are supported
```

Keep the default (`library="ak"`), or convert the awkward array afterwards.

### The first read pays the compilation

Compiling costs far more than reading one basket. The compiled module bytes are kept in two places, so the cost is paid once:

- on the interpretation, which compiles once per branch;
- in `uproot_custom.detree.cache`, keyed by the reader's structural signature (`uproot_custom.detree.compiler.frontend.describe_reader`), which is shared by every branch in the process with the same reader structure.

The cache lives for the life of the process and is never evicted.

The reader itself is rebuilt per basket, and a fresh machine is built from the cached module bytes for every run, so arrays returned by an earlier basket are never overwritten by a later one.

## Errors

| Error | Raised when |
| ----- | ----------- |
| `ReaderContractError` | a `@reader` class breaks the contract, or is defined outside a `.py` file. The check runs when the class is defined, so it surfaces as an import error |
| `UnsupportedNode` | a compiled method uses a construct outside the subset, or `build_detree_reader` returned a class without `@reader`; the message names the method and line |
| `NotImplementedError` | the selected backend's `build_*_reader` method is missing |
| `detree.spec.errors.AssertionFailed` | an `assert` in a read path failed. The message is yours; the exception also carries `function`, `ip` and `cursor` |
| `detree.spec.errors.InvalidByteCount` | a byte count was read that lacks `kByteCountMask` — the read is out of step with the bytes, usually one field too early or too late |
| `detree.spec.errors.StreamUnderflow` | the read asked for more bytes than the entry holds |
| `detree.spec.errors.ReadLengthMismatch` | the read did not end on the entry's offset (`event N: expected X bytes, read Y`), or an entry offset is missing |

The last four come from the machine and are subclasses of `detree.spec.errors.DetreeError`. Under the Python executor, `uproot_custom.detree.interp`, the same reader raises plain `AssertionError` and `ValueError` instead, without the `function`/`ip`/`cursor` fields — that difference is the quickest way to tell which executor produced an error.

## See also

- [Write a Detree reader](../tutorial/write-a-reader.md) — the guided version of this page.
- [Debug a reader](../tutorial/debug-a-reader.md) — the two executors, module dumps, and common problems.
- [The Python + C++ route](../advanced/index.md) — what to do when the subset is too small.
