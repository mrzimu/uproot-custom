# Write a Detree reader

A branch is decoded by a **reader**, and a **factory** decides which reader a class gets. This page writes both for one class, `TOverrideStreamer`, whose `Streamer` method inserts an extra mask that the built-in factories cannot know about.

The reader is a *Detree reader*: it declares its output buffers, constants and sub-readers as fields, and its `read` method is Python source that the compiler lowers to a detree-vm module. Nothing in `read` runs as Python during a read; `data` does, once per basket, to hand the filled buffers to the factory. This is the Detree route, the recommended one; the [Python + C++ route](../advanced/index.md) is the alternative.

## What you will build

By the end of this page you will have three pieces:

| Piece | What it does |
| ----- | ------------ |
| a `@reader` class | declares the buffers and decodes one entry of `TOverrideStreamer` |
| a `Factory` | matches the class, builds the reader, and turns the buffers into an awkward record |
| a registration block | adds the factory to `registered_factories` and the branch to `AsCustom.target_branches` |

The branch then decodes to a record with two fields, the same on every backend.

## The Factory API

Every factory inherits from `Factory`. Four methods matter, and one of them decides whether the class matches.

Uproot-custom iterates over all registered factory classes **sorted by `priority()` in descending order** and uses the first one whose `build_factory` returns a non-`None` result.

### `priority` (classmethod)

Controls the order in which factories are tried. Factories with **higher** priority are called first. The default value is `10`.

Override this method when your factory needs to run before or after the built-in ones:

```python
class MySpecialFactory(Factory):
    @classmethod
    def priority(cls):
        return 20   # run before most built-in factories (default 10)
```

For reference, the built-in factories use the following priorities:

| Priority | Factory | Why |
| :------: | ------- | --- |
| 20 | `CStyleArrayFactory` | Must match C-style arrays before other factories see the same type name. |
| 15 | `AnyPointerFactory` | Must see an object pointer (`MyClass*`) before the factories that would treat it as an inline class and skip its pointer header. |
| 10 | All other built-in factories | Default. |
| 0 | `AnyClassFactory` | Catch-all fallback — should run last. |

```{tip}
When registering a custom factory that targets a specific class name, the default priority (`10`) is usually sufficient because `build_factory` already returns `None` for non-matching classes. Increase the priority only when your factory competes with a built-in factory for the same type name. The one to watch is a class that arrives behind a pointer: `AnyPointerFactory` runs at 15, so a factory that must own such a member needs a priority above 15.
```

### Constructor

The constructor receives all parameters needed by the reader-building and awkward-building methods. At minimum it must accept a `name` (usually `fName` from the streamer info).

(method-build-factory)=
### `build_factory` (classmethod)

Called during factory-tree construction. Parameters:

- `top_type_name: str` — the top-level type name, with `std::` prefixes stripped (e.g. `vector` for `std::vector<std::map<int, float>>`).

- `cur_streamer_info: dict` — the streamer dictionary for the current data member. Use it to decide whether this factory is applicable. Example:

    ```python
    {'@fUniqueID': 0,
    '@fBits': 16777216,
    'fName': 'm_int',
    'fTitle': '',
    'fType': 3,
    'fSize': 4,
    'fArrayLength': 0,
    'fArrayDim': 0,
    'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
    'fTypeName': 'int'}
    ```

- `all_streamer_info: dict` — maps every class name to the list of its members' streamer dictionaries. Use it to look up nested classes:

    ```python
    >>> all_streamer_info["TSimpleObject"]
    [{'@fUniqueID': 0,
    '@fBits': 16777216,
    'fName': 'TObject',
    'fTitle': 'Basic ROOT object',
    'fType': 66,
    'fSize': 0,
    'fArrayLength': 0,
    'fArrayDim': 0,
    'fMaxIndex': array([          0, -1877229523,           0,           0,           0],
            dtype='>i4'),
    'fTypeName': 'BASE',
    'fBaseVersion': 1},
    {'@fUniqueID': 0,
    '@fBits': 16777216,
    'fName': 'm_int',
    'fTitle': '',
    'fType': 3,
    'fSize': 4,
    'fArrayLength': 0,
    'fArrayDim': 0,
    'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
    'fTypeName': 'int'},
    ...
    ]
    ```

    Build sub-factories for nested members:

    ```python
    sub_factories = []
    for member in all_streamer_info["TSimpleObject"]:
        sub_fac = build_factory(member)
        sub_factories.append(sub_fac)
    ```

- `item_path: str` — the regularized object-path of the branch, plus one `.` and the member name for every level below it: `/my_tree:entry/m_obj`, then `/my_tree:entry/m_obj.m_sub`. An STL element reuses its member's name, so the element of a `vector<int> m_vec` member sees `/my_tree:entry/m_vec.m_vec`. The path never contains a type name. Use it for path-specific logic, such as claiming a class in one branch only.

- `**kwargs` — reserved for future use.

````{important}
`cur_streamer_info` does not describe the same thing at every node:

| The class is… | `fName` | `fTypeName` | `top_type_name` |
| ------------- | ------- | ----------- | --------------- |
| the whole branch | the class name | absent | the class name |
| one member of a split class | the member name, e.g. `m_obj` | the class name, e.g. `TOverrideStreamer` | the class name |

Match on `top_type_name` when you mean "this class":

```python
if top_type_name != "TOverrideStreamer":
    return None
return cls(cur_streamer_info["fName"])
```

Matching on `fName` works only when the class happens to be the whole branch. For a member it returns `None` without an error, the built-in `AnyClassFactory` takes the node, and the read fails later with a byte-count error that says nothing about the factory.
````

**Return** an instance of the factory if the node matches, or `None` to pass to the next registered factory.

### `build_detree_reader`

Return the reader for this node:

```python
def build_detree_reader(self):
    return OverrideStreamerReader(self.name)
```

A composite factory builds its sub-readers first and passes them in:

```python
class AnyClassFactory(GroupFactory):
    def build_detree_reader(self):
        return uproot_custom.detree.builtin.AnyClassReader(
            self.name,
            elements=tuple(s.build_detree_reader() for s in self.sub_factories),
        )
```

Each backend has its own method (`build_detree_reader`, `build_python_reader`, `build_cpp_reader`), and only the selected backend's method is called. A factory may implement all three; the others are simply unused. See [choosing a technical route](../concepts/choosing-a-route.md).

### `make_awkward_content(raw_data)`

Convert `raw_data` (the value returned by the reader's `data()` method) into an `awkward.contents.Content`.

```{seealso}
[`awkward` direct constructors](https://awkward-array.org/doc/main/user-guide/how-to-create-constructors.html)
```

### `make_awkward_form`

Return an `awkward.forms.Form` that describes the data layout. This is used for lazy evaluation.

```{seealso}
[`awkward` forms reference](https://awkward-array.org/doc/main/reference/generated/ak.forms.Form.html)
```

---

## The Detree reader

A Detree reader is a class decorated with `@reader` that inherits from `Reader` and declares what it produces:

```python
import numpy as np

from uproot_custom.detree import Buffer, Reader, reader


@reader
class OverrideStreamerReader(Reader):
    ints = Buffer("i")
    doubles = Buffer("d")

    def read(self, stream):
        stream.skip_TObject()
        self.ints.append(stream.read_int32())
        mask = stream.read_uint32()
        assert mask == 0x12345678, "unexpected mask"
        self.doubles.append(stream.read_double())

    def data(self):
        return np.asarray(self.ints), np.asarray(self.doubles)
```

### Declaring fields

| Field | Purpose |
| ----- | ------- |
| `Const(default, type=..., choices=..., ge=..., le=...)` | a constructor argument fixed for the branch; readable in `read`, never writable |
| `Buffer(type, *, init=(), from_const=None, kind="data")` | a typed output array; `type` is a `struct` typecode (`"i"`), a NumPy dtype (`np.int32`) or a dtype string (`"int32"`), and it is positional — `Buffer(typecode=...)` is not a keyword. `kind="offsets"` marks a buffer of cumulative offsets that begins at its `init` value |
| `State(type, init)` | a variable that survives the entries of one basket, reset to `init` when the reader is rebuilt for the next basket; the only kind of attribute a read path may assign |
| `Child()` | exactly one sub-reader |
| `ChildList()` | an ordered tuple of sub-readers; a `for` loop over it is unrolled |

See [the Detree reference](../reference/detree-dsl.md) for the full contract.

### The read path

`read` is compiled and runs once per entry inside the machine. Three rules cover almost everything:

- every `stream.*` call consumes bytes and advances the cursor — the methods mirror the Python `BinaryStream` one for one;
- `self.<buffer>.append(value)` appends to a declared buffer; a local variable lives for one call, while a declared `State` survives to the next entry;
- `assert` is the only way to fail. `raise` is rejected when the class is defined, so report a bad record as `assert condition, "message"`.

### `data()`

`data()` runs in Python, once per basket, after the machine has filled the buffers. It must return exactly the shape your factory's `make_awkward_content` expects — here a tuple of two arrays. Two readers of the same class must agree on that shape even if they decode the bytes differently, which is what makes the backends interchangeable.

### Returning it from the factory

`build_detree_reader` returns the reader instance, fully wired with its sub-readers. The factory does not read anything itself.

## Worked example: `TArray`

Take the `TArrayFactory` as a concrete example of the factory side. `TArray` nodes store a `uint32_t` size followed by that many typed elements.

### The factory

`TArrayFactory` matches any `TArray*` type name, creates the corresponding typed reader, and converts the offsets + data arrays into an `awkward` `ListOffsetArray`:

```{code-block} python
---
caption: "`TArrayFactory`"
---
import awkward
import awkward as ak
import awkward.contents
import awkward.forms
import awkward.index
import uproot_custom
from uproot_custom import Factory
from uproot_custom.consts import DTYPE_TO_TYPECODE

class TArrayFactory(Factory):
    """
    This class reads TArray from a binary paerser.

    TArray includes TArrayC, TArrayS, TArrayI, TArrayL, TArrayL64, TArrayF, and TArrayD.
    Corresponding dtype is int8, int16, int32, int64, int64, float32, and float64 respectively.
    """

    typename2dtype = {
        "TArrayC": "int8",
        "TArrayS": "int16",
        "TArrayI": "int32",
        "TArrayL": "int64",
        "TArrayL64": "int64",
        "TArrayF": "float32",
        "TArrayD": "float64",
    }

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is in `cls.typenames`.
        """
        if top_type_name not in cls.typename2dtype:
            return None

        dtype = cls.typename2dtype[top_type_name]
        return cls(name=cur_streamer_info["fName"], dtype=dtype)

    def __init__(self, name: str, dtype: str):
        super().__init__(name)
        self.dtype = dtype

    def build_detree_reader(self):
        return uproot_custom.detree.builtin.TArrayReader(
            self.name,
            typecode=DTYPE_TO_TYPECODE[self.dtype],
        )

    def make_awkward_content(self, raw_data):
        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data),
        )

    def make_awkward_form(self):
        return ak.forms.ListOffsetForm("i64", ak.forms.NumpyForm(self.dtype))
```

### The reader

`TArrayReader` shows the other common shape: a `Const` that fixes the element type at construction, and a `Buffer` whose dtype comes from that constant. One class then serves every `TArray` variant.

```python
import numpy as np

from uproot_custom.detree import Buffer, Const, Reader, reader


@reader
class TArrayReader(Reader):
    typecode = Const("i", type=str, choices=("b", "B", "h", "H", "i", "I", "q", "Q", "f", "d"))
    offsets = Buffer("q", init=(0,), kind="offsets")
    values = Buffer(from_const="typecode")

    def read(self, stream):
        size = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + size)
        stream.read_bulk(self.values, size)

    def data(self):
        return np.asarray(self.offsets), np.asarray(self.values)
```

`kind="offsets"` tells the compiler the buffer holds cumulative offsets, and `init=(0,)` gives the leading zero. `stream.read_bulk` reads `size` values in one call instead of a Python loop — the machine has an instruction for it, and the loop would not be compiled any faster.

## Register and read

Registration happens in two places, both before the branch's interpretation is first computed — see [get started](../getting-started.md#step-2-register-the-branch): the factory class goes into `registered_factories`, and the branch path goes into `target_branches`.

```python
import uproot
import uproot_custom as uc

from my_module.factories import OverrideStreamerFactory

uc.registered_factories.add(OverrideStreamerFactory)
uc.AsCustom.target_branches.add("/my_tree:override_streamer/m_obj")

uc.set_backend("detree")   # the code default is cpp

f = uproot.open("file.root")
array = f["my_tree/override_streamer/m_obj"].array()
```

The branch's interpretation now reads `AsCustom(TOverrideStreamer)`, and the array is a record with an `m_int` and an `m_double` field. The path must be the *regularized object-path*; [investigate your data](investigate-data.md) shows how to obtain it.

## What the compiler accepts

The read path must stay inside a small subset of Python:

| Allowed | Examples |
| ------- | -------- |
| statements | `if`/`else`, `while`, `for _ in range(n)`, `for child in self.<ChildList>`, `assert`, assignment to a local, a `State`, or `stream.cursor` |
| expressions | integer and boolean arithmetic and comparisons, `and`/`or`/`not`, `if` expressions, `bool()`, `int()` |
| buffers | `buf.append(x)`, `len(buf)`, `buf[-1]` |
| stream | the scalar `read_*` methods, `read_into`, `read_bulk`, `skip` and the `skip_*` helpers, `next_offset_after`, the reference helpers |

| Not allowed | Use instead |
| ----------- | ----------- |
| imports, `try`, `with`, `raise`, `lambda`, comprehensions | none — rewrite the reader, or take the Python + C++ route |
| dict, set, or list literals | none |
| `print`, numpy, `isinstance`, arbitrary function calls | `data()`, which runs in Python |
| writing a plain `self.<attr>` | declare it as `State(...)` |

A construct outside the subset fails with `ReaderContractError` when the class is defined, or `UnsupportedNode` when the reader is compiled, naming the method and line. The full tables are in the [Detree reference](../reference/detree-dsl.md#the-compilable-subset).

If the read path genuinely needs one of the constructs in the second table, Detree is the wrong route for that branch. The other route is **Python + C++**: write the reader as a Python `IReader` first ([stage 1](../advanced/python-reader.md)), then port the same logic to C++ ([stage 2](../advanced/cpp-reader.md)) because the Python half is too slow to ship. The factory, the registration and the awkward code stay unchanged, because a factory may implement `build_detree_reader` alongside `build_python_reader` and `build_cpp_reader` — only the selected backend's method runs. [Choosing a technical route](../concepts/choosing-a-route.md) compares the two.

This can be a per-branch decision. The backend is a runtime choice and the readers share one factory, so the branches that fit the subset keep running on Detree, and only the one that does not pays for the other route.

## When it fails

| What you see | Raised when | Fix |
| ------------ | ----------- | --- |
| `ReaderContractError: <Class>.<method>: line N: Try cannot be compiled` | a read path breaks the subset, at class definition time — so importing your module fails | rewrite the read path, or take the Python + C++ route |
| `ReaderContractError: ... source is not available; readers must live in a .py file` | the reader was defined in a notebook or a REPL | move it into a module |
| `UnsupportedNode: <Class> must be decorated with @reader at root` | `build_detree_reader` returned a class without `@reader` | decorate it |
| `UnsupportedNode: ... line N: ...` | a construct the per-method check did not catch, found while compiling | rewrite it, or take the Python + C++ route |
| `detree.spec.errors.AssertionFailed: <your message> function=... ip=... cursor=...` | an `assert` in a read path failed | the message is yours; `cursor` says how far the read got |
| `detree.spec.errors.InvalidByteCount: fNBytes=... lacks kByteCountMask` | the read is out of step with the bytes, usually a header consumed in the wrong place | compare against the raw bytes and check the field before it |

A failed `assert` looks different under the two executors: the machine raises `AssertionFailed` with the position attached, while `uproot_custom.detree.interp` raises a plain `AssertionError` carrying only your message. That difference is the quickest way to tell which executor produced an error.

## Next steps

- [Debug a reader](debug-a-reader.md) — compile without a file and compare the two executors.
- [Package your project](package-your-project.md) — ship the factory and reader.
- [Detree reference](../reference/detree-dsl.md) — every field and the whole compilable subset.
