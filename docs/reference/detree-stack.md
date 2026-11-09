# Detree reader backend

The **detree** reader backend is one of the ways `AsCustom` can decode a branch. Instead of walking a tree of Python or C++ readers over the basket, it takes the declarative reader tree, compiles it into a Detree-VM module, and executes that module on a Detree machine. The branch still reports its interpretation as `AsCustom`; only the byte-level reader changes.

```{important}
The detree backend is experimental. It is meant for validation, benchmarking, and experiments rather than for production analysis. The `cpp` backend remains the default and the supported production path. Detree-VM's official release will ship the Rust machine only.
```

## Install

Detree-VM is an optional dependency:

```sh
pip install "uproot-custom[detree]"
```

## Writing a reader the detree backend can run

A custom factory that only implements `build_python_reader` or `build_cpp_reader` can still be read by those backends. To make it work with the detree backend too, add `build_detree_reader`, returning a *detree reader*:

```python
class IntListFactory(Factory):
    # ... build_factory, make_awkward_content, make_awkward_form, ...

    def build_detree_reader(self):
        return IntListReader(self.name)
```

The detree reader declares what it reads and leaves the read path to the compiler:

```python
import numpy as np

from uproot_custom.detree.decl import Buffer, Reader, reader


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
| `Const(value, type=..., choices=..., ge=..., le=...)` | a constructor argument fixed for the branch; readable in `read`, never writable |
| `Buffer(typecode, init=(), from_const=None, kind="data")` | a typed output array; `kind` is `"data"`, `"offsets"`, or `"count"`; `from_const` takes the typecode from a `Const` field, which is how one class serves every dtype |
| `State(type, init)` | a per-basket variable; the only kind of attribute a read path may assign. A `State(str, ...)` holds a name slot |
| `Child()` | exactly one sub-reader |
| `ChildList()` | an ordered tuple of sub-readers; a `for` loop over it is unrolled |

The `@reader` decorator checks the following at class definition time:

- the class is defined in a `.py` file — the compiler re-reads its source, so a class typed into a notebook or a REPL is refused;
- no `__init__`; declare fields instead and pass values as keyword arguments, e.g. `IntListReader(name, typecode="d")`;
- `read(self, stream)` and `data(self)` are required; `read_many`, `read_until`, and `read_many_memberwise` take `(self, stream, argument)` and default to loops over `read`, except `read_many_memberwise` (see below);
- the second parameter is named `stream`;
- field names do not start with `_`, are not inherited and overridden, and do not collide with the method names;
- a read path assigns only to declared `State` fields (or `stream.cursor`); a plain attribute is invisible to the compiled code, and a `Const` cannot be written.

Implement `read_many_memberwise` when the reader can appear in a memberwise-stored container (an element of `vector<T>`, or a key or value of `map<K, V>`). The default one throws at run time rather than silently reading the wrong bytes.

### The compilable subset

`read`, `read_many`, `read_until`, and `read_many_memberwise` are compiled from source, so they must stay within a small subset of Python:

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

A construct outside the subset fails with `ReaderContractError` (when the class is defined) or `UnsupportedNode` (when the reader is compiled), naming the method and the offending line. Rewrite the reader, or use a different reader backend; there is no fallback for a reader the compiler rejects.

## How the detree backend works

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

There is no fallback to another backend. When a factory cannot build a detree reader, the first read raises

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

## Testing and debugging a detree reader

Compile the reader without touching a file to catch contract and subset errors early:

```python
from uproot_custom.detree.compiler.frontend import compile_reader, describe_reader

reader = IntListFactory("branch").build_detree_reader()
print(describe_reader(reader))

raw, signature = compile_reader(reader)
```

`describe_reader` prints the structural signature that keys the compilation cache, and `compile_reader` returns the module bytes and that signature, raising `UnsupportedNode` when the reader cannot be compiled.

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

`interp` runs the reader methods as plain Python — `print`, `pdb`, and ordinary tracebacks work there — while `read_data` compiles and runs the same tree on the machine. A disagreement between the two localizes the problem to the reader or to the compiler. For a fixed-width branch, `byte_offsets` is `None` and the call needs the fixed entry size instead, as `nbyte=`.

Set `UPROOT_CUSTOM_DETREE_DUMP_MODULES=1` to print the module's instructions each time a reader is compiled. The old name `UPROOT_CUSTOM_JIT_DUMP_MODULES` is still honoured.

## Common problems

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `NotImplementedError: ... does not implement build_detree_reader` | the factory has no `build_detree_reader` | add `build_detree_reader`, or use another reader backend |
| `Unknown reader backend: ...` | bad `UPROOT_CUSTOM_READER_BACKEND` value | use `cpp`, `python`, `forth`, or `detree` |
| `AssertionError: Only awkward arrays are supported` | `library="np"` or `"pd"` | read with the default awkward library |
| `ReaderContractError: ... source is not available; readers must live in a .py file` | the reader was defined in a notebook or REPL | move it into a module |
| `ReaderContractError: ... self.<name> is assigned ...` | a plain attribute is written in a read path | declare it as `State(<default>)` |
| `UnsupportedNode: ... line N: ...` | a construct outside the compilable subset | rewrite the read path, or use another reader backend |
| arrays differ between backends | `data()` does not match `make_awkward_content` | compare the two executors as shown above |
