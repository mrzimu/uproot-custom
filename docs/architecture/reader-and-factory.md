# Reader and factory interface

`uproot-custom` uses a `reader`/`factory` mechanism to balance performance and flexibility. `reader`s are implemented in C++, do the actual reading from binary stream. `factory`s are implemented in Python, manage `reader`s, and reconstruct the final `awkward` array.

## Reader interface

### Base class: `IElementReader`

`reader` in C++ should derive from the `IElementReader` interface, which has two pure virtual methods:

- `read`: called by parent `reader` to read data from the binary stream.
- `data`: called after reading is done, to return the read-out data in `numpy` arrays or any Python nested containers filled with `numpy` arrays.

There are extra 3 virtual methods that can be overridden to handle special cases:

- `read_many`: called when reading multiple elements in one go, such as reading c-style arrays. Some classes may have only one header with multiple elements following it. In this case, `read_many` can be overridden to read handle such case.

- `read_until`: called when reading elements until a certain position in the binary stream.

- `read_many_memberwise`: called when reading multiple elements in a member-wise fashion. "Member-wise" means that the first member of all elements are read first, then the second member of all elements are read, and so on. This is used when reading STL containers in some specific cases.

```{code-block} cpp
---
caption: `IElementReader`
lineno-start: 1
emphasize-lines: 11-12
---
class IElementReader {
  protected:
    const std::string m_name;

  public:
    IElementReader( std::string name ) : m_name( name ) {}
    virtual ~IElementReader() = default;

    virtual const std::string name() const { return m_name; }

    virtual void read( BinaryBuffer& buffer ) = 0;
    virtual py::object data() const           = 0;

    virtual uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) {
        for ( int32_t i = 0; i < count; i++ ) { read( buffer ); }
        return count;
    }

    virtual uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) {
        uint32_t cur_count = 0;
        while ( buffer.get_cursor() < end_pos )
        {
            read( buffer );
            cur_count++;
        }
        return cur_count;
    }

    virtual uint32_t read_many_memberwise( BinaryBuffer& buffer, const int64_t count ) {
        if ( count < 0 )
        {
            std::stringstream msg;
            msg << name() << "::read_many_memberwise with negative count: " << count;
            throw std::runtime_error( msg.str() );
        }
        return read_many( buffer, count );
    }
};
```

```{note}
- A `std::string name` is required for each `reader`, which is used to print debug information.
- Several extended virtual methods are also provided. These methods will be called when reading c-style arrays or STL containers.
```

### `BinaryBuffer` class

`BinaryBuffer` is a helper class to read binary data from a `uint8_t*` buffer. It provides methods to read basic types, skip bytes, and handle `fNBytes`+`fVersion` header.

Reading methods include:
- `const T read<T>()`: Read a value of type `T` from the buffer, and advance the cursor.
- `const int16_t read_fVersion()`: Equivalent to `read<int16_t>()`.
- `const uint32_t read_fNBytes()`: Read `fNBytes` from the buffer, check the mask, and return the actual number of bytes.
- `const std::string read_null_terminated_string()`: Read a null-terminated string from the buffer.
- `const std::string read_obj_header()`: Read the object header from the buffer, return the object's name if present. Can be used when `ObjectHeaderReader` is not used.
- `const std::string read_TString()`: Read a `TString` from the buffer

Skipping methods include:
- `void skip(const size_t nbytes)`: Skip `nbytes` bytes.
- `void skip_fVersion()`: Skip the `fVersion` (2 bytes).
- `void skip_fNBytes()`: Equivalent to `read_fNBytes()`, will check the mask.
- `void skip_null_terminated_string()`: Skip a null-terminated string.
- `void skip_obj_header()`: Skip the object header.
- `void skip_TObject()`: Skip a `TObject`.

Other methods include:
- `const uint8_t* get_data() const`: Get the start of the data buffer.
- `const uint8_t* get_cursor() const`: Get the current cursor position.
- `const uint32_t* get_offsets() const`: Get the entry offsets of the data buffer.
- `const uint64_t* entries() const`: Get the number of entries of the data buffer.
- `void debug_print( const size_t n = 100 ) const`: Print the next `n` bytes from the current cursor for debugging.


### Accept sub-`reader`s

When reading nested classes, a `reader` may require sub-`reader`s to read the nested data members. For example, `STLSeqReader` needs a sub-`reader` to read the element type of the STL sequence, such as `int`, `float`, or a custom class. In this case, the sub-`reader` can be passed to the constructor of the parent `reader`.

In the constructor, the sub-`reader` should be passed as a `std::shared_ptr<IElementReader>`. This is because other `readers` are constructed in Python, so the ownership of the `reader` should be shared between C++ and Python.

`uproot-custom.hh` already define a type alias `using SharedReader = shared_ptr<IElementReader>;` for convenience.


### Transform `std::vector` to `numpy` array without copying

When returning data in `data` method, `reader` can use `make_array` helper function to transform `std::shared_ptr<std::vector<T>>` to `numpy` array without copying:

```cpp
std::shared_ptr<std::vector<int>> data = std::make_shared<std::vector<int>>();
data->push_back(1);
data->push_back(2);
data->push_back(3);

py::array_t<int> np_array = make_array(data);
```

### Declaring `reader` to Python

`uproot-custom` uses `pybind11` to declare C++ `reader`s to Python. A helper function `declare_reader` is provided to simplify the declaration. When implementing your own `reader`, you should declare it to Python like this:

```cpp
PYBIND11_MODULE( my_cpp_reader, m) {
    declare_reader<MyReaderClass, constructor_arg1_type, constructor_arg2_type, ...>(m, "MyReaderClass");
}
```

- The `constructor_argN_type` are the types of the constructor arguments of your `reader`. If your `reader` has no constructor arguments, you can omit them.
- The second argument of `declare_reader` is the name of your `reader` in Python. In this example, it is `"MyReaderClass"`.

Then you can import `MyReaderClass` in Python:

```python
from my_cpp_reader import MyReaderClass
```

### Debugging message

`uproot-custom` provides a `debug_print` method to print debugging message. The print will only be performed when `UPROOT_DEBUG` macro is defined, or `UPROOT_DEBUG` environment variable is set:

```cpp
// Will print "The reader name is Bob"
debug_print("The reader name is %s", "Bob");

// Call buffer.debug_print(50), print next 50 bytes from current cursor
debug_print( buffer, 50 )
```

## Factory interface

`factory` in Python should derive from the `BaseFactory` interface, which has four methods to be implemented:

- `build_factory`: Match the data member and instantiate the `factory` if matched, otherwise return `None`.
- `build_cpp_reader`: Called to create the C++ `reader`.
- `make_awkward_content`: Called to reconstruct the final `awkward` content with the raw data read by the C++ `reader`.
- `make_awkward_form`: Called to generate the `awkward` form.

To select the appropriate `factory` for a data member, `uproot-custom` loops over all registered `factory` classes, and calls their `build_factory` method. The first non-`None` return value will be used.

### Constructor

The constructor of `factory` should receive all necessary parameters for the `factory` to build C++ reader, make `awkward` content and form. The constructor should at least receive a `name` parameter, which is usually the `fName` in the `streamer info`.

(method-build-factory)=
### Class method `build_factory`

This method is called when instatiating factories. It should be a class method.

It receives following parameters:

- `top_type_name: str`: The top-level type name of current data member.

    Any `std::` prefixes will be stripped. For example, for `std::vector<std::map<int, float>>`, the `top_type_name` is `vector`.

- `cur_streamer_info: dict`: The streamer info `dict` of the current data member.

    `factory ` can use this information to decide whether it can handle this node, and to generate the configuration `dict`.

    An example of `cur_streamer_info` is:

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

    For other type of data members, such as STL containers or nested classes, some other attributes may be present.

- `all_streamer_info: dict`: A `dict` mapping all available streamer names to their members' streamer info `dict`. 

    `factory` can use this information to look up the streamer info of any nested classes.

    For example, you can retrieve the streamer information of `TSimpleObject` like:

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

    And use it to build sub-factories for nested data members:

    ```python
    sub_factories = []
    for member in all_streamer_info["TSimpleObject"]:
        sub_fac = build_factory(member)
        sub_factories.append(sub_fac)
    ```

- `item_path: str`: The absolute path from the root node to the current data member.

    It is useful when some special handling is needed for certain nodes.

- `**kwargs`: Any extra keyword arguments that might be needed.

When current data member is not suitable for the `factory`, it should return `None`, so that `uproot-custom` will try next `factory`, until one return an instance of itself.

When current data member is suitable for the `factory`, it should return an instance of itself, with all necessary parameters passed to the constructor.

### Method `build_cpp_reader`

This method is called to instatiate the C++ reader. For non-bottom-level factories, it should also instatiate sub-readers for nested data members and combine them together to the parent reader.

### Method `make_awkward_content`

This method is called to construct `awkward` content with given raw data read by the C++ `reader`.

It receives following parameters:

- `raw_data: Any`: The raw data read by the C++ `reader`, returned by its `data` method.

The `factory` should return `awkward.contents.Content` object.

```{seealso}
Refer to [`awkward` direct constructors](https://awkward-array.org/doc/main/user-guide/how-to-create-constructors.html) for more details about `awkward` contents.
```

### Method `make_awkward_form`

This method is called when building the `awkward` forms.

The `factory` should return an `awkward.forms.Form` object.

```{seealso}
Refer to [awkward forms](https://awkward-array.org/doc/main/reference/generated/ak.forms.Form.html) for more details about `awkward` forms.
```

## Example of reader and factory

Take the `TArrayReader` and `TArrayFactory` as an example. This pair of `reader` and `factory` handles `TArray` nodes in the data tree.

The `TArrayReader`:
- Reads `fSize`, then reads `fSize` number of `T` elements from the binary stream in its `read` method.
- The read-out data is stored in two vectors: `m_offsets` and `m_data`
- These two vectors are converted to `numpy` arrays and returned in its `data` method, which is called after reading is done.

```{code-block} cpp
---
caption: `TArrayReader`
---
template <typename T>
class TArrayReader : public IElementReader {
    private:
    SharedVector<int64_t> m_offsets;
    SharedVector<T> m_data;

    public:
    TArrayReader( std::string name )
        : IElementReader( name )
        , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) )
        , m_data( std::make_shared<std::vector<T>>() ) {}

    void read( BinaryBuffer& buffer ) override {
        auto fSize = buffer.read<uint32_t>();
        m_offsets->push_back( m_offsets->back() + fSize );
        for ( auto i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<T>() ); }
    }

    py::object data() const override {
        auto offsets_array = make_array( m_offsets );
        auto data_array    = make_array( m_data );
        return py::make_tuple( offsets_array, data_array );
    }
};
```

---

In `TArrayFactory`,

- `build_factory` method matches the data member and instantiates the `TArrayFactory`
- `build_cpp_reader` method creates the C++ `TArrayReader`.
- `make_awkward_content` method constructs the `awkward` content with the raw data returned by `TArrayReader`.
- `make_awkward_form` method generates the corresponding `awkward` form.

```{code-block} python
---
caption: `TArrayFactory`
---
class TArrayFactory(Factory):
    """
    This class reads TArray from a binary paerser.

    TArray includes TArrayC, TArrayS, TArrayI, TArrayL, TArrayL64, TArrayF, and TArrayD.
    Corresponding ctype is u1, u2, i4, i8, i8, f, and d.
    """

    typenames = {
        "TArrayC": "i1",
        "TArrayS": "i2",
        "TArrayI": "i4",
        "TArrayL": "i8",
        "TArrayL64": "i8",
        "TArrayF": "f",
        "TArrayD": "d",
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
        if top_type_name not in cls.typenames:
            return None

        ctype = cls.typenames[top_type_name]
        return cls(name=cur_streamer_info["fName"], ctype=ctype)

    def __init__(self, name: str, ctype: str):
        super().__init__(name)
        self.ctype = ctype

    def build_cpp_reader(self):
        return {
            "i1": uproot_custom.cpp.TArrayCReader,
            "i2": uproot_custom.cpp.TArraySReader,
            "i4": uproot_custom.cpp.TArrayIReader,
            "i8": uproot_custom.cpp.TArrayLReader,
            "f": uproot_custom.cpp.TArrayFReader,
            "d": uproot_custom.cpp.TArrayDReader,
        }[self.ctype](self.name)

    def make_awkward_content(self, raw_data):
        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data),
        )

    def make_awkward_form(self):
        return ak.forms.ListOffsetForm(
            "i64",
            ak.forms.NumpyForm(PrimitiveFactory.ctype_primitive_map[self.ctype]),
        )
```
