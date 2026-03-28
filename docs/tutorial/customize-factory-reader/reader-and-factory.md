# Reader & factory interface

Uproot-custom splits the work between two layers:

- **Reader** — reads binary data from the ROOT byte buffer. It can be written
  in **Python** (for rapid development and debugging) or **C++** (for
  production performance).
- **Factory** (Python) — orchestrates readers, and converts their output into
  `awkward` arrays.

This page describes the Python reader and factory interfaces, then presents a
worked example using the Python backend.

---

## Reader interface (Python)

### Base class: `IReader`

Every Python reader must inherit from `uproot_custom.readers.python.IReader`
and implement two methods:

| Method | Purpose |
| ------ | ------- |
| `read(buffer)` | Consume bytes from the buffer for one entry. |
| `data()` | Return all accumulated data as `numpy` arrays (or nested containers of them). |

Three additional methods handle special reading patterns (override only when
needed):

| Method | When it is called |
| ------ | ----------------- |
| `read_many(buffer, count)` | Reading a fixed number of elements (e.g. c-style arrays). Override when multiple elements share a single header. |
| `read_until(buffer, end_pos)` | Reading elements until a byte position is reached. |
| `read_many_memberwise(buffer, count)` | Member-wise reading: all first members, then all second members, etc. Used by some STL containers. |

```{code-block} python
---
caption: "`IReader` — base class"
lineno-start: 1
emphasize-lines: 5-6
---
class IReader:
    def __init__(self, name: str):
        self.name = name

    def read(self, buffer: BinaryBuffer) -> None:
        raise NotImplementedError

    def data(self):
        raise NotImplementedError

    def read_many(self, buffer: BinaryBuffer, count: int) -> int:
        for _ in range(count):
            self.read(buffer)
        return count

    def read_until(self, buffer: BinaryBuffer, end_pos: int) -> int:
        count = 0
        while buffer.cursor < end_pos:
            self.read(buffer)
            count += 1
        return count

    def read_many_memberwise(self, buffer: BinaryBuffer, count: int) -> int:
        raise NotImplementedError
```

```{note}
Every reader requires a `name: str` for debug output.
```

### `BinaryBuffer`

`BinaryBuffer` wraps a byte buffer and provides convenience methods for
reading ROOT binary data.

**Reading**
- `read_uint8() → int`, `read_uint16()`, `read_uint32()`, `read_uint64()`: Read unsigned integers.
- `read_int8() → int`, `read_int16()`, `read_int32()`, `read_int64()`: Read signed integers.
- `read_float() → float`, `read_double() → float`: Read floating-point values.
- `read_bool() → bool`: Read a boolean value.
- `read_fVersion() → int`: Read `fVersion` (signed 16-bit).
- `read_fNBytes() → int`: Read `fNBytes` from the buffer, check the mask, and return the actual number of bytes.
- `read_null_terminated_string() → str`: Read a null-terminated string from the buffer.
- `read_obj_header() → str`: Read the object header, return the object's name if present.
- `read_TString() → str`: Read a `TString` from the buffer.

**Skipping**
- `skip(n)`: Skip `n` bytes.
- `skip_fVersion()`: Skip the `fVersion` (2 bytes).
- `skip_fNBytes()`: Equivalent to `read_fNBytes()`, will check the mask.
- `skip_null_terminated_string()`: Skip a null-terminated string.
- `skip_obj_header()`: Skip the object header.
- `skip_TObject()`: Skip a `TObject`.

**Miscellaneous**
- `cursor`: Current cursor position (byte index into the buffer).
- `entries`: Number of entries in the data buffer.
- `offsets`: Entry offsets of the data buffer.

### Accepting sub-readers

Composite readers accept sub-readers for nested types.
Pass sub-readers as `IReader` instances because they are managed by Python's
garbage collector.

### Debug output

Set the `UPROOT_DEBUG` environment variable to enable debug printing. When
enabled, the module-level `debug_print` function becomes an alias for
`print`:

```python
import os
os.environ["UPROOT_DEBUG"] = "1"

# Now debug_print(...) calls will produce output
```

You can also print the current buffer state:

```python
def read(self, buffer):
    print(buffer)   # shows the next N bytes from the current cursor
    ...
```

---

## Factory interface (Python)

Every Python factory must inherit from `Factory` and implement four
methods:

| Method | Purpose |
| ------ | ------- |
| `priority` (classmethod) | Return an `int` controlling match order. Higher values are tried first. Default is `10`. |
| `build_factory` (classmethod) | Match a streamer node; return an instance if matched, `None` otherwise. |
| `build_python_reader` | Create and return the Python reader for this node. |
| `make_awkward_content(raw_data)` | Convert raw `numpy` data into an `awkward.contents.Content`. |
| `make_awkward_form` | Return an `awkward.forms.Form` describing the data layout. |

Uproot-custom iterates over all registered factory classes **sorted by
`priority()` in descending order** and uses the first one whose
`build_factory` returns a non-`None` result.

### `priority` (classmethod)

Controls the order in which factories are tried. Factories with **higher**
priority are called first. The default value is `10`.

Override this method when your factory needs to run before or after the
built-in ones:

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
| 10 | All other built-in factories | Default. |
| 0 | `AnyClassFactory` | Catch-all fallback — should run last. |

```{tip}
When registering a custom factory that targets a specific class name, the
default priority (`10`) is usually sufficient because `build_factory` already
returns `None` for non-matching classes. Increase the priority only when your
factory competes with a built-in factory for the same type name.
```

### Constructor

The constructor receives all parameters needed for the three runtime methods.
At minimum it must accept a `name` (usually `fName` from the streamer info).

(method-build-factory)=
### `build_factory` (classmethod)

Called during factory-tree construction. Parameters:

- `top_type_name: str` — the top-level type name, with `std::` prefixes
  stripped (e.g. `vector` for `std::vector<std::map<int, float>>`).

- `cur_streamer_info: dict` — the streamer dictionary for the current data
  member. Use it to decide whether this factory is applicable. Example:

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

- `all_streamer_info: dict` — maps every class name to the list of its
  members' streamer dictionaries. Use it to look up nested classes:

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

- `item_path: str` — the dot-separated path from the root to this node.
  Useful for path-specific logic.

- `**kwargs` — reserved for future use.

**Return** an instance of the factory if the node matches, or `None` to pass
to the next registered factory.

### `build_python_reader`

Instantiate and return the Python reader. For composite factories, also build
sub-readers and wire them together.

### `make_awkward_content(raw_data)`

Convert `raw_data` (the value returned by the reader's `data()` method) into
an `awkward.contents.Content`.

```{seealso}
[`awkward` direct constructors](https://awkward-array.org/doc/main/user-guide/how-to-create-constructors.html)
```

### `make_awkward_form`

Return an `awkward.forms.Form` that describes the data layout. This is used
by `dask` for lazy evaluation.

```{seealso}
[`awkward` forms reference](https://awkward-array.org/doc/main/reference/generated/ak.forms.Form.html)
```

---

## Worked example: `TArray`

Take the `TArrayReader` / `TArrayFactory` pair as a concrete example.
`TArray` nodes store a `uint32_t` size followed by that many typed elements.

### Python reader

`TArrayReader` reads `fSize`, then reads `fSize` elements. It accumulates
offsets and data using Python's `array` module:

```{code-block} python
---
caption: "`TArrayReader` (Python)"
---
from array import array
import numpy as np

from uproot_custom.readers.python import IReader, BinaryBuffer, DTYPE_TO_READER, DTYPE_TO_TYPECODE


class TArrayReader(IReader):
    def __init__(self, name, dtype):
        super().__init__(name)
        self.dtype = dtype
        self.typecode = DTYPE_TO_TYPECODE[dtype]
        self._data = array(self.typecode)
        self.offsets = array("q", [0])
        self.buffer_reader = DTYPE_TO_READER[dtype]

    def read(self, buffer):
        fSize = buffer.read_uint32()
        self.offsets.append(self.offsets[-1] + fSize)
        for _ in range(fSize):
            self._data.append(self.buffer_reader(buffer))

    def data(self):
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="int64")
        data_array = np.frombuffer(self._data.tobytes(), dtype=self.dtype)
        return offsets_array, data_array
```

---

### Python factory

`TArrayFactory` matches any `TArray*` type name, creates the corresponding
typed Python reader, and converts the offsets + data arrays into an `awkward`
`ListOffsetArray`:

```{code-block} python
---
caption: "`TArrayFactory`"
---
import uproot_custom.readers.python

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

    def build_cpp_reader(self):
        return {
            "int8": uproot_custom.readers.cpp.TArrayCReader,
            "int16": uproot_custom.readers.cpp.TArraySReader,
            "int32": uproot_custom.readers.cpp.TArrayIReader,
            "int64": uproot_custom.readers.cpp.TArrayLReader,
            "float32": uproot_custom.readers.cpp.TArrayFReader,
            "float64": uproot_custom.readers.cpp.TArrayDReader,
        }[self.dtype](self.name)

    def build_python_reader(self):
        return uproot_custom.readers.python.TArrayReader(self.name, self.dtype)

    def make_awkward_content(self, raw_data):
        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data),
        )

    def make_awkward_form(self):
        return ak.forms.ListOffsetForm("i64", ak.forms.NumpyForm(self.dtype))
```



---

```{seealso}
Once your Python reader is working correctly, you can port the logic to C++
for production performance. See [](port-to-cpp.md) for the C++ `IReader` API,
`BinaryBuffer` reference, pybind11 bindings, and a worked C++ version of
`TArrayReader`.
```

```{admonition} Next step
---
class: hint
---
You now understand the Reader and Factory interfaces. Move on to
[Project setup](project-setup.md) to create a proper Python package that
wires your factory and reader together.
```
