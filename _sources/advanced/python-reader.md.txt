# Stage 1: the Python implementation

Every reader on the Python + C++ route starts here. The Python implementation is an `IReader` whose `read` method is ordinary Python, so it can do anything: `try` blocks, imports, numpy calls, dictionary lookups, calls into other packages. It is where the byte layout is worked out and debugged, and it later serves as the oracle the C++ implementation is checked against.

```{note}
This is the **`python` backend**. It is not Detree: a Detree reader is Python *source* that is compiled to bytecode, while this reader is executed as Python. It is also not Detree's Python executor (`uproot_custom.detree.interp`), which only runs a Detree reader's methods for debugging.
```

```{note}
`uproot_custom.python` is also the reference implementation of the ROOT byte layout. It is kept independent of the Detree built-in readers on purpose: when the two disagree, that disagreement is a finding.
```

## What this stage is for

- **Getting the logic right.** A `try` around an optional header, a dictionary lookup keyed by a name read from the file, a call into another package: none of these compile, and the Python implementation accepts them all.
- **Debugging interactively.** `print`, `pdb` and ordinary tracebacks work; inside the machine they do not.
- **Being the oracle.** Once the C++ implementation exists, this one stays in the repository and the two are compared basket by basket.

It is **not** the deployment target: it runs at Python speed, several times slower than Detree. See [the rest of the route](index.md).

## The IReader interface

Every Python reader must inherit from `uproot_custom.python.IReader` and implement two methods:

| Method | Purpose |
| ------ | ------- |
| `read(stream)` | Consume bytes from the stream for one entry. |
| `data()` | Return all accumulated data as `numpy` arrays (or nested containers of them). |

Three additional methods handle special reading patterns (override only when needed):

| Method | When it is called |
| ------ | ----------------- |
| `read_many(stream, count)` | Reading a fixed number of elements (e.g. c-style arrays). Override when multiple elements share a single header. |
| `read_until(stream, end_pos)` | Reading elements until a byte position is reached. |
| `read_many_memberwise(stream, count)` | Member-wise reading: all first members, then all second members, etc. Used by some STL containers. |

```{code-block} python
---
caption: "`IReader` — base class"
lineno-start: 1
emphasize-lines: 5-6
---
class IReader:
    def __init__(self, name: str):
        self.name = name

    def read(self, stream: BinaryStream) -> None:
        raise NotImplementedError

    def data(self):
        raise NotImplementedError

    def read_many(self, stream: BinaryStream, count: int) -> int:
        for _ in range(count):
            self.read(stream)
        return count

    def read_until(self, stream: BinaryStream, end_pos: int) -> int:
        count = 0
        while stream.cursor < end_pos:
            self.read(stream)
            count += 1
        return count

    def read_many_memberwise(self, stream: BinaryStream, count: int) -> int:
        raise NotImplementedError
```

```{note}
Every reader requires a `name: str` for debug output.
```

## BinaryStream

`BinaryStream` wraps a byte stream and provides convenience methods for reading ROOT binary data.

**Reading**
- `read_uint8() → int`, `read_uint16()`, `read_uint32()`, `read_uint64()`: Read unsigned integers.
- `read_int8() → int`, `read_int16()`, `read_int32()`, `read_int64()`: Read signed integers.
- `read_float() → float`, `read_double() → float`: Read floating-point values.
- `read_bool() → bool`: Read a boolean value.
- `read_fVersion() → int`: Read `fVersion` (signed 16-bit).
- `read_fNBytes() → int`: Read `fNBytes` from the stream, check the mask, and return the actual number of bytes.
- `read_null_terminated_string() → str`: Read a null-terminated string from the stream.
- `read_obj_header() → str`: Read the object header, return the object's name if present.
- `read_TString() → str`: Read a `TString` from the stream.

**Skipping**
- `skip(n)`: Skip `n` bytes.
- `skip_fVersion()`: Skip the `fVersion` (2 bytes).
- `skip_fNBytes()`: Equivalent to `read_fNBytes()`, will check the mask.
- `skip_null_terminated_string()`: Skip a null-terminated string.
- `skip_obj_header()`: Skip the object header.
- `skip_TObject()`: Skip a `TObject`.

**Miscellaneous**
- `cursor`: Current cursor position (byte index into the stream).
- `entries`: Number of entries in the data stream.
- `offsets`: Entry offsets of the data stream.

## Sub-readers

Composite readers accept sub-readers for nested types. Pass sub-readers as `IReader` instances because they are managed by Python's garbage collector.

## Debug output

Set the `UPROOT_DEBUG` environment variable to enable debug printing. When enabled, the module-level `debug_print` function becomes an alias for `print`:

```python
import os
os.environ["UPROOT_DEBUG"] = "1"

# Now debug_print(...) calls will produce output
```

You can also print the current stream state:

```python
def read(self, stream):
    print(stream)   # shows the next N bytes from the current cursor
    ...
```

## The factory method

A factory on this route names both stages: `build_python_reader` returns the Python implementation, and [`build_cpp_reader`](cpp-reader.md) returns the C++ one.

```python
class OverrideStreamerFactory(Factory):
    # ... build_factory, priority, make_awkward_content, make_awkward_form ...

    def build_python_reader(self):
        return OverrideStreamerPythonReader(self.name)

    def build_cpp_reader(self):
        return cpp.OverrideStreamerReader(self.name)
```

Only the selected backend's method is called. `make_awkward_content` and `make_awkward_form` are shared, because both implementations return the same shape from `data()`.

## Worked example: `TArray`

Take the `TArrayReader` / `TArrayFactory` pair as a concrete example. `TArray` nodes store a `uint32_t` size followed by that many typed elements.

### Python reader

`TArrayReader` reads `fSize`, then reads `fSize` elements. It accumulates offsets and data using Python's `array` module:

```{code-block} python
---
caption: "`TArrayReader` (Python)"
---
from array import array
import numpy as np

from uproot_custom.python import IReader, BinaryStream, DTYPE_TO_READER, DTYPE_TO_TYPECODE


class TArrayReader(IReader):
    def __init__(self, name, dtype):
        super().__init__(name)
        self.dtype = dtype
        self.typecode = DTYPE_TO_TYPECODE[dtype]
        self._data = array(self.typecode)
        self.offsets = array("q", [0])
        self.buffer_reader = DTYPE_TO_READER[dtype]

    def read(self, stream):
        fSize = stream.read_uint32()
        self.offsets.append(self.offsets[-1] + fSize)
        for _ in range(fSize):
            self._data.append(self.buffer_reader(stream))

    def data(self):
        offsets_array = np.frombuffer(self.offsets.tobytes(), dtype="int64")
        data_array = np.frombuffer(self._data.tobytes(), dtype=self.dtype)
        return offsets_array, data_array
```

## Comparing the two stages

Once [`build_cpp_reader`](cpp-reader.md) exists, read the same branch under each backend and compare the arrays:

```python
import uproot_custom as uc

compiled = f["my_tree/my_branch"].array()          # cpp, the default

with uc.use_backend("python"):
    interpreted = f["my_tree/my_branch"].array()

assert compiled.to_list() == interpreted.to_list()
```

The arrays come from the same factory (`make_awkward_content`), so a difference means the two `read` paths disagree — which is exactly the bug you are looking for. Because both paths share the awkward layer, the comparison is sharper than checking the values you expected.

If a Detree reader for the same class also exists, it can be compared the same way; that check is described in [Debug a reader](../tutorial/debug-a-reader.md).
