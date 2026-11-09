# Detree reader backend

The **detree** reader backend is one of the ways `AsCustom` can decode a
branch. Instead of walking a tree of Python or C++ readers over the basket, it
takes the declarative reader tree, compiles it into a Detree-VM module, and
executes that module on a Detree machine. The branch still reports its
interpretation as `AsCustom`; only the byte-level reader changes.

```{important}
The detree backend is experimental. It is meant for validation, benchmarking,
and experiments rather than for production analysis. The `cpp` backend remains
the default and the supported production path.
```

## How the detree backend works

```{mermaid}
flowchart TB
    F["Factory"] --> R["native reader tree"]
    R --> C["compile_reader"]
    C --> M["Detree module"]
    M --> VM["Detree machine"]
    VM --> B["buffers and state"]
    B --> D["Reader.data()"]
    D --> A["awkward content"]
```

Every backend shares the same `Factory`: it decides which reader to build and
how the raw data becomes an awkward array. Only the byte-level reader differs,
so a branch decodes to the same array on every backend.

The reader is *declarative*. It declares its output buffers, per-basket state,
constants, and sub-readers as fields; its `read` method is ordinary Python
source that the compiler turns into bytecode. Nothing in `read` runs as Python
during a read — `data` does, once per basket, to turn the filled buffers into
the tuple, list, or arrays your factory consumes.

## Reader backend, machine, and factory method

Three different switches are easy to confuse:

| Term | What it selects | Set by |
| ---- | --------------- | ------ |
| reader backend | which implementation reads the bytes: `cpp`, `python`, `forth`, or `detree` | `UPROOT_CUSTOM_READER_BACKEND` or `uproot_custom.backend` |
| machine | which Detree-VM implementation runs a module: `python`, `cpp`, or `rust` | `UPROOT_CUSTOM_DETREE_BACKEND` or `uproot_custom.detree` |
| factory method | which reader a factory builds: `build_cpp_reader`, `build_python_reader`, `build_forth_reader`, or `build_detree_reader` | the factory implementation |

The machine is only consulted when the reader backend is `detree`;
`UPROOT_CUSTOM_DETREE_BACKEND` has no effect on the other backends.

## Install

Detree-VM is an optional dependency:

```sh
pip install "uproot-custom[detree]"
```

Detree-VM always provides its Python reference machine, and its wheels carry a
compiled machine (Rust by default). In this workspace, install the sibling
checkout before the project:

```sh
DETREE_SHIP_BACKEND=both uv pip install -e ../detree-vm
uv pip install -e . --group dev
```

## Quick start

Select the backend before reading the branch. A context manager is the least
surprising way to scope the choice:

```python
import uproot
import uproot_custom as uc

with uc.use_backend("detree"):
    with uproot.open("file.root") as file:
        array = file["/my_tree:my_branch"].array()
```

To make the choice global, set `UPROOT_CUSTOM_READER_BACKEND=detree` before the
first read, or call `uc.set_backend("detree")`. The environment variable is
read once; use `set_backend` or `use_backend` to change the selection
afterwards.

No separate registration is needed: the detree backend reuses
`AsCustom.target_branches`. Select the backend and every branch already claimed
by `AsCustom` is read with it. `AsCustom` remains the interpretation, so the
branch prints as `AsCustom(vector<double>)`.

## Choosing the machine

`uproot_custom.detree.get_impl()` reports which Detree-VM machine executes the
compiled module; the default is `rust`.

| Value | Machine |
| ----- | ------- |
| `rust` | the Rust machine, shipped in the Detree-VM wheel |
| `python` | the Python reference machine; always available, slowest |
| `cpp` | the C++ machine, if Detree-VM was built with it |

Select it with `set_impl`, or temporarily with `use_impl`:

```python
from uproot_custom.detree import set_impl, use_impl

set_impl("python")

with use_impl("cpp"):
    ...
```

`UPROOT_CUSTOM_DETREE_BACKEND` seeds the selection when it is first read:

```python
import os

os.environ["UPROOT_CUSTOM_DETREE_BACKEND"] = "python"
```

A value that names no machine raises `ValueError: Invalid backend: ...`. A
machine that is not built in the installed Detree-VM raises its
`BackendUnavailable` on the first read, for example
`backend 'cpp' is unavailable: libcppdetree was not found`.

## What the detree backend can read

A branch is readable with this backend when its factory implements
`build_detree_reader`. Every built-in factory does, except for one:

| Factory | Native reader |
| ------- | ------------- |
| `PrimitiveFactory` | `PrimitiveReader` |
| `STLSeqFactory` (`vector`, `list`, `set`, `multiset`, `unordered_set`, `unordered_multiset`, `std::array`) | `STLSeqReader` |
| `STLMapFactory` (`map`, `multimap`, `unordered_map`, `unordered_multimap`) | `STLMapReader` |
| `STLStringFactory` | `STLStringReader` |
| `TStringFactory` | `TStringReader` |
| `TArrayFactory` | `TArrayReader` |
| `TObjectFactory` | `TObjectReader` |
| `CStyleArrayFactory` | `CStyleArrayReader` |
| `GroupFactory` | `GroupReader` |
| `AnyClassFactory` | `AnyClassReader` |
| `AnyPointerFactory` | `AnyPointerReader` |
| `EmptyFactory` | `EmptyReader` |
| `BaseObjectFactory` | none yet |

`BaseObjectFactory` reads the `BASE` member of a class that inherits from
another class (`fType` 0). Such a branch cannot be read by the detree backend
and raises `NotImplementedError` on its first read. Classes that only inherit
`TObject` are unaffected: that base is a `TObjectFactory` member (`fType` 66).

## Limitations

### A branch is compiled or it is not

There is no fallback to another backend. When the detree backend cannot build a
native reader, the first read raises

```{code-block} console
NotImplementedError: <Factory> does not build a native reader; use a different
reader backend
```

The failure is deliberate: a silent switch would make a benchmark, or a bug
report, describe a machine that never ran. Select another backend for that
read instead.

Note that the failure happens on the first read, not when the file is opened:
the interpretation and its awkward form are built before the factory is asked
for a reader.

### Awkward arrays only

All reader backends decode through `AsCustom`, which requires the awkward
library. Reading with `library="np"` or `library="pd"` raises

```{code-block} console
AssertionError: Only awkward arrays are supported
```

Keep the default (`library="ak"`), or convert the awkward array afterwards.

### Class inheritance beyond `TObject` is not supported yet

See `BaseObjectFactory` above. A class whose streamer has a non-`TObject` base
member cannot be read by the detree backend; use another reader backend for it.

### The first read pays the compilation

Compiling costs far more than reading one basket. The compiled module is kept
in two places, so the cost is paid once:

- on the interpretation, which compiles once per branch;
- in `uproot_custom.detree.cache`, keyed by the reader's structural signature
  (`uproot_custom.detree.compiler.frontend.describe_reader`), which is shared by every branch in
  the process with the same reader structure.

The cache lives for the life of the process and is never evicted.

The reader itself is rebuilt per basket, and the machine is reset before every
run, so arrays returned by an earlier basket are never overwritten by a later
one.

### Threads

A `Compiled` keeps one machine per thread and per machine backend, and the
reader and its buffers belong to a single basket. Two threads may therefore
read the same branch at the same time without sharing registers or buffers.

A `detree.Machine` is not thread-safe. If you build one yourself, do not share
it between threads.

## Writing a reader the detree backend can run

A custom factory that only implements `build_python_reader` or
`build_cpp_reader` can still be read by those backends. To make it work with
the detree backend too, add `build_detree_reader`, returning a *native reader*:

```python
class IntListFactory(Factory):
    # ... build_factory, make_awkward_content, make_awkward_form, ...

    def build_detree_reader(self):
        return IntListReader(self.name)
```

The native reader declares what it reads and leaves the read path to the
compiler:

```python
import numpy as np

from uproot_custom.detree.decl import Buffer, Reader, reader


@reader
class IntListReader(Reader):
    """
    A `uint32` count followed by that many `int32` values.
    """

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

`read` is compiled and runs inside the machine. `data` is ordinary Python that
runs on the filled buffers, so keep it consistent with your factory's
`make_awkward_content` — the same requirement as for a Python or C++ reader.

### Fields

| Field | Purpose |
| ----- | ------- |
| `Const(value, type=..., choices=..., ge=..., le=...)` | a constructor argument fixed for the branch; readable in `read`, never writable |
| `Buffer(typecode, init=(), from_const=None, kind="data")` | a typed output array; `kind` is `"data"`, `"offsets"`, or `"count"`; `from_const` takes the typecode from a `Const` field, which is how one class serves every dtype |
| `State(type, init)` | a per-basket variable; the only kind of attribute a read path may assign. A `State(str, ...)` holds a name slot |
| `Child()` | exactly one sub-reader |
| `ChildList()` | an ordered tuple of sub-readers; a `for` loop over it is unrolled |

The `@reader` decorator checks the following at class definition time:

- the class is defined in a `.py` file — the compiler re-reads its source, so
  a class typed into a notebook or a REPL is refused;
- no `__init__`; declare fields instead and pass values as keyword arguments,
  e.g. `IntListReader(name, typecode="d")`;
- `read(self, stream)` and `data(self)` are required; `read_many`,
  `read_until`, and `read_many_memberwise` take `(self, stream, argument)` and
  default to loops over `read`, except `read_many_memberwise` (see below);
- the second parameter is named `stream`;
- field names do not start with `_`, are not inherited and overridden, and do
  not collide with the method names;
- a read path assigns only to declared `State` fields (or `stream.cursor`); a
  plain attribute is invisible to the compiled code, and a `Const` cannot be
  written.

Implement `read_many_memberwise` when the reader can appear in a
memberwise-stored container (an element of `vector<T>`, or a key or value of
`map<K, V>`). The default one throws at run time rather than silently reading
the wrong bytes.

### The compilable subset

`read`, `read_many`, `read_until`, and `read_many_memberwise` are compiled from
source, so they must stay within a small subset of Python:

| Allowed | What |
| ------- | ---- |
| statements | `if`/`else`, `while`, `for _ in range(n)`, `for child in self.<ChildList>`, `assert`, `pass`, assignment to a local, a `State`, or `stream.cursor` |
| integer and boolean expressions | `+ - * // / % << >> & \| ^ ~`, unary `-`, comparisons, `if` expression, `and`/`or`/`not` in conditions, `bool()`, `int()` |
| buffers | `buf.append(x)`, `len(buf)`, `buf[-1]` |
| stream | the scalar `read_*` methods, `read_into`, `read_bulk`, `read_fNBytes`, `read_fVersion`, `read_null_terminated_string`, `skip` and the `skip_*` helpers, `next_offset_after`, `cursor`, `entries`, `initial_cursor_position`, `has_ref`, `ref_*`, `set_*_ref` |
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

A construct outside the subset fails with `ReaderContractError` (when the class
is defined) or `UnsupportedNode` (when the reader is compiled), naming the
method and the offending line. Rewrite the reader, or use a different reader
backend; there is no fallback for a reader the compiler rejects.

## Testing and debugging a native reader

Compile the reader without touching a file to catch contract and subset errors
early:

```python
from uproot_custom.detree.compiler.frontend import compile_reader, describe_reader

reader = IntListFactory("branch").build_detree_reader()
print(describe_reader(reader))

raw, signature = compile_reader(reader)
```

`describe_reader` prints the structural signature that keys the compilation
cache, and `compile_reader` returns the module bytes and that signature, raising
`UnsupportedNode` when the reader cannot be compiled.

To run one basket and compare the two executors of the same reader:

```python
from uproot_custom.detree import interp
from uproot_custom.detree.run import read_data

entry = file["/my_tree:my_branch"]
reader = entry.interpretation.factory.build_detree_reader()
basket = entry.basket(0)

interp.read_basket(reader, basket.data, basket.byte_offsets, basket.member("fKeylen"))
print(reader.data())

reader = entry.interpretation.factory.build_detree_reader()
print(read_data(reader, basket.data, basket.byte_offsets, basket.member("fKeylen")))
```

`interp` runs the reader methods as plain Python — `print`, `pdb`, and ordinary
tracebacks work there — while `read_data` compiles and runs the same tree on the
machine. A disagreement between the two localizes the problem to the reader or
to the compiler. For a fixed-width branch, `byte_offsets` is `None` and the call
needs the fixed entry size instead, as `nbyte=`.

Set `UPROOT_CUSTOM_JIT_DUMP_MODULES=1` to print the module's instructions each
time a reader is compiled.

## Common problems

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `NotImplementedError: ... does not build a native reader` | the factory does not implement `build_detree_reader` | use another reader backend, or add a native reader |
| `Unknown reader backend: ...` | bad `UPROOT_CUSTOM_READER_BACKEND` value | use `cpp`, `python`, `forth`, or `detree` |
| `AssertionError: Only awkward arrays are supported` | `library="np"` or `"pd"` | read with the default awkward library |
| `ValueError: Invalid backend: ...` | unknown machine name | use `rust`, `python`, or `cpp` |
| `BackendUnavailable: backend 'cpp' is unavailable` | that machine is not built in the installed Detree-VM | use `rust` or `python`, or install Detree-VM with the C++ machine |
| `ReaderContractError: ... source is not available; readers must live in a .py file` | the reader was defined in a notebook or REPL | move it into a module |
| `ReaderContractError: ... self.<name> is assigned ...` | a plain attribute is written in a read path | declare it as `State(<default>)` |
| `UnsupportedNode: ... line N: ...` | a construct outside the compilable subset | rewrite the read path, or use another reader backend |
| arrays differ between backends | `data()` does not match `make_awkward_content` | compare the two executors as shown above |
