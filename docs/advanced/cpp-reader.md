# Stage 2: the C++ implementation

This is what production runs on the Python + C++ route. It is the fastest executor and the most expensive thing to ship: write it after the [Python implementation](python-reader.md) has established the byte layout, and expect to pin the uproot-custom version and rebuild for every Python version you support.

The two stages must decode the same bytes into the same `data()` shape. The factory shares `make_awkward_content` and `make_awkward_form`, so a mismatch between the implementations shows up as a wrong array, not as a build error.

## Version pinning and the ABI

A C++ reader is compiled against the Uproot-custom header, the pybind11 it exposes, and one Python ABI. Each of those can move independently of your project:

| Coupled to | What happens when it moves |
| ---------- | -------------------------- |
| the Uproot-custom header | `IReader` is compatible only within one minor version; a newer minor may change the vtable and the module fails to load |
| the pybind11 minor version | the Python-visible base type stops resolving: `ImportError: generic_type: type "xxx" referenced unknown base type "uproot::IReader"` |
| the Python ABI | each Python minor version needs a rebuilt wheel |

A downstream project therefore pins the exact Uproot-custom minor version and the matching pybind11 minor version, ships a wheel per Python version, and rebuilds when either moves. This is the cost the [Detree path](../concepts/choosing-a-route.md) removes; [version requirements](../reference/version-requirements.md) lists the pinned versions.

## C++ `IReader` base class

Every C++ reader must inherit from `IReader` and implement two pure-virtual methods:

| Method | Purpose |
| ------ | ------- |
| `read(BinaryStream&)` | Consume bytes from the stream for one entry. |
| `data() → py::object` | Return all accumulated data as `numpy` arrays (or nested containers of them). |

The same optional methods are available as in Python:

| Method | When it is called |
| ------ | ----------------- |
| `read_many(stream, count)` | Reading a fixed number of elements. |
| `read_until(stream, end_pos)` | Reading elements until a byte position. |
| `read_many_memberwise(stream, count)` | Member-wise reading for STL containers. |

```{code-block} cpp
---
caption: "`IReader` — C++ base class"
lineno-start: 1
emphasize-lines: 11-12
---
class IReader {
  protected:
    const std::string m_name;

  public:
    IReader( std::string name ) : m_name( name ) {}
    virtual ~IReader() = default;

    virtual const std::string name() const { return m_name; }

    virtual void read( BinaryStream& stream ) = 0;
    virtual py::object data() const           = 0;

    virtual uint32_t read_many( BinaryStream& stream, const int64_t count ) {
        for ( int32_t i = 0; i < count; i++ ) { read( stream ); }
        return count;
    }

    virtual uint32_t read_until( BinaryStream& stream, const uint8_t* end_pos ) {
        uint32_t cur_count = 0;
        while ( stream.get_cursor() < end_pos )
        {
            read( stream );
            cur_count++;
        }
        return cur_count;
    }

    virtual uint32_t read_many_memberwise( BinaryStream& stream, const int64_t count ) {
        if ( count < 0 )
        {
            std::stringstream msg;
            msg << name() << "::read_many_memberwise with negative count: " << count;
            throw std::runtime_error( msg.str() );
        }
        return read_many( stream, count );
    }
};
```

---

## C++ `BinaryStream`

The C++ `BinaryStream` wraps a `uint8_t*` stream with the same convenience methods as the Python version:

**Reading**
- `const T read<T>()`: Read a value of type `T` from the stream, and advance the cursor.
- `const int16_t read_fVersion()`: Equivalent to `read<int16_t>()`.
- `const uint32_t read_fNBytes()`: Read `fNBytes` from the stream, check the mask, and return the actual number of bytes.
- `const std::string read_null_terminated_string()`: Read a null-terminated string from the stream.
- `const std::string read_obj_header()`: Read the object header from the stream, return the object's name if present.
- `const std::string read_TString()`: Read a `TString` from the stream.

**Skipping**
- `void skip(const size_t nbytes)`: Skip `nbytes` bytes.
- `void skip_fVersion()`: Skip the `fVersion` (2 bytes).
- `void skip_fNBytes()`: Equivalent to `read_fNBytes()`, will check the mask.
- `void skip_null_terminated_string()`: Skip a null-terminated string.
- `void skip_obj_header()`: Skip the object header.
- `void skip_TObject()`: Skip a `TObject`.

### Counted regions

An object framed by its byte count declares how many bytes follow it. Both forms below check that the block consumed exactly that many, and throw `std::runtime_error` with `expected N, got M`:

```cpp
void read( BinaryStream& stream ) override {
    auto frame = stream.check_nbytes();
    auto fVersion = stream.read_fVersion();
    if ( fVersion == 0 ) stream.skip( 4 );
    for ( auto& reader : m_element_readers ) { reader->read( stream ); }
}
```

- `void check_nbytes_start()`: read the masked `fNBytes` and remember where the region ends. Regions nest, so a framed sub-reader does not disturb its caller.
- `void check_nbytes_end()`: fail unless the cursor is at the end of the innermost region.
- `void check_nbytes_end( const uint8_t* expected )`: fail unless the cursor is at `expected`, for a region whose size was computed rather than read.
- `CountedRegion check_nbytes()`: open the region and check it when the bound guard leaves scope — the C++ form of Python's `with`. Bind it (`auto frame = ...`); the return type is `[[nodiscard]]` because a bare statement would close the region immediately.
- `size_t open_frames() const`: the number of regions still waiting for their end.

A block that throws drops the region without a second exception, so the original error survives. The Python form of this API is in [the Python reader page](python-reader.md#binarystream).

**Miscellaneous**
- `const uint8_t* get_data() const`: Get the start of the data stream.
- `const uint8_t* get_cursor() const`: Get the current cursor position.
- `const uint32_t* get_offsets() const`: Get the entry offsets of the data stream.
- `const uint64_t* entries() const`: Get the number of entries of the data stream.
- `void debug_print( const size_t n = 100 ) const`: Print the next `n` bytes from the current cursor for debugging.

---

## Accepting sub-readers

Composite readers (e.g. `STLSeqReader`) accept sub-readers for nested types. Pass sub-readers as `std::shared_ptr<IReader>` (aliased as `SharedReader`) because ownership is shared between C++ and Python.

---

## Zero-copy `numpy` conversion

Use the `make_array` helper to convert a `std::shared_ptr<std::vector<T>>` into a `numpy` array **without copying**:

```cpp
std::shared_ptr<std::vector<int>> data = std::make_shared<std::vector<int>>();
data->push_back(1);
data->push_back(2);
data->push_back(3);

py::array_t<int> np_array = make_array(data);
```

---

## Exposing a reader to Python

Uproot-custom uses `pybind11` for bindings. The `declare_reader` helper simplifies declaration:

```cpp
PYBIND11_MODULE( my_cpp_reader, m) {
    declare_reader<MyReaderClass, constructor_arg1_type, constructor_arg2_type, ...>(m, "MyReaderClass");
}
```

- `constructor_argN_type` — the types of the constructor arguments (`SharedReader`, `std::string`, etc.). Omit if the constructor takes only `name`.
- The second argument to `declare_reader` is the Python-visible class name.

Import in Python:

```python
from my_cpp_reader import MyReaderClass
```

---

## C++ debug output

Use the `debug_print` helper for conditional logging. Messages are only emitted when the `UPROOT_DEBUG` macro is defined at compile time **or** the `UPROOT_DEBUG` environment variable is set at runtime:

```cpp
// Will print "The reader name is Bob"
debug_print("The reader name is %s", "Bob");

// Call stream.debug_print(50), print next 50 bytes from current cursor
debug_print( stream, 50 )
```

---

## Adding `build_cpp_reader` to the factory

Once the C++ reader is ready, add a `build_cpp_reader` method to the factory alongside the Detree reader. This is the **only** Python-side change needed — `make_awkward_content` and `make_awkward_form` remain exactly the same, because both readers return data in the same structure.

---

## Side-by-side comparison: `OverrideStreamerReader`

The following tabs show the same `OverrideStreamerReader` (from the [pipeline example](../concepts/how-it-works.md#complete-example-putting-it-all-together)) in Python and C++. Notice how the reading logic is identical — only the language syntax differs.

`````{tab-set}

````{tab-item} Python
```{code-block} python
---
caption: "`OverrideStreamerReader` (Python)"
lineno-start: 1
---
from array import array
import numpy as np
from uproot_custom.python import IReader


class OverrideStreamerReader(IReader):
    def __init__(self, name):
        super().__init__(name)
        self.m_ints = array("i")       # int32
        self.m_doubles = array("d")    # float64

    def read(self, stream):
        stream.skip_TObject()                        # skip base class
        self.m_ints.append(stream.read_int32())      # m_int

        mask = stream.read_uint32()                  # custom mask
        if mask != 0x12345678:
            raise RuntimeError(f"Unexpected mask: {mask:#x}")

        self.m_doubles.append(stream.read_double())  # m_double

    def data(self):
        return np.asarray(self.m_ints), np.asarray(self.m_doubles)
```
````

````{tab-item} C++
```{code-block} cpp
---
caption: "`OverrideStreamerReader` (C++)"
lineno-start: 1
---
#include <cstdint>
#include <memory>
#include <vector>

#include "uproot-custom/uproot-custom.hh"

using namespace uproot;

class OverrideStreamerReader : public IReader {
  public:
    OverrideStreamerReader( std::string name )
        : IReader( name )
        , m_data_ints( std::make_shared<std::vector<int>>() )
        , m_data_doubles( std::make_shared<std::vector<double>>() ) {}

    void read( BinaryStream& stream ) {
        stream.skip_TObject();                          // skip base class
        m_data_ints->push_back( stream.read<int>() );   // m_int

        auto mask = stream.read<uint32_t>();             // custom mask
        if ( mask != 0x12345678 )
            throw std::runtime_error( "Unexpected mask: " +
                                      std::to_string( mask ) );

        m_data_doubles->push_back( stream.read<double>() ); // m_double
    }

    py::object data() const {
        return py::make_tuple( make_array( m_data_ints ),
                               make_array( m_data_doubles ) );
    }

  private:
    std::shared_ptr<std::vector<int>> m_data_ints;
    std::shared_ptr<std::vector<double>> m_data_doubles;
};

PYBIND11_MODULE( my_reader_cpp, m ) {
    declare_reader<OverrideStreamerReader, std::string>( m, "OverrideStreamerReader" );
}
```
````

`````

Then add `build_cpp_reader` to the factory:

```{code-block} python
---
caption: "Adding C++ reader to `OverrideStreamerFactory`"
---
from .my_reader_cpp import OverrideStreamerReader as OverrideStreamerCppReader

class OverrideStreamerFactory(Factory):
    def build_cpp_reader(self):
        return OverrideStreamerCppReader(self.name)

    # build_python_reader, make_awkward_content, make_awkward_form
    # remain exactly the same as before
```

---

## Worked example: `TArray` in C++

Compare with the [Python version](python-reader.md#worked-example-tarray) — the reading logic is identical; only the language syntax differs:

```{code-block} cpp
---
caption: "`TArrayReader` (C++) — same logic as the Python version"
---
template <typename T>
class TArrayReader : public IReader {
    private:
    SharedVector<int64_t> m_offsets;
    SharedVector<T> m_data;

    public:
    TArrayReader( std::string name )
        : IReader( name )
        , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) )
        , m_data( std::make_shared<std::vector<T>>() ) {}

    void read( BinaryStream& stream ) override {
        auto fSize = stream.read<uint32_t>();
        m_offsets->push_back( m_offsets->back() + fSize );
        for ( auto i = 0; i < fSize; i++ ) { m_data->push_back( stream.read<T>() ); }
    }

    py::object data() const override {
        auto offsets_array = make_array( m_offsets );
        auto data_array    = make_array( m_data );
        return py::make_tuple( offsets_array, data_array );
    }
};
```

Then add `build_cpp_reader` to `TArrayFactory`:

```{code-block} python
---
caption: Adding C++ reader support to `TArrayFactory`
emphasize-lines: 2-12
---
class TArrayFactory(Factory):
    def build_cpp_reader(self):
        return {
            "int8": uproot_custom.cpp.TArrayCReader,
            "int16": uproot_custom.cpp.TArraySReader,
            "int32": uproot_custom.cpp.TArrayIReader,
            "int64": uproot_custom.cpp.TArrayLReader,
            "float32": uproot_custom.cpp.TArrayFReader,
            "float64": uproot_custom.cpp.TArrayDReader,
        }[self.dtype](self.name)

    def build_python_reader(self):
        return uproot_custom.python.TArrayReader(self.name, self.dtype)

    # ... make_awkward_content and make_awkward_form remain unchanged
```

---

## Selecting the C++ stage

After implementing `build_cpp_reader`, select the backend:

```python
import uproot_custom as uc
uc.set_backend("cpp")
```

`"cpp"` is the code default, so a project that ships only C++ readers needs no call — but a project that also selects Detree elsewhere must set it explicitly.

```{seealso}
See [](../concepts/choosing-a-route.md) for the trade-offs and backend selection.
```
