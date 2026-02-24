# Example 1: `Streamer` method is overridden

Goal: handle a class whose `Streamer` overrides the default layout by inserting
an extra mask. We will inspect the bytes, write a Python reader, wrap it with a
factory, register it, then read with Uproot. Finally, we show how to port the
reader to C++ for production speed.

```{seealso}
A full example can be found in the [example repository](https://github.com/mrzimu/uproot-custom-example).
```

We define a demo class `TOverrideStreamer` whose `Streamer` method is overridden to show how to read such classes using uproot-custom.

There are 2 member variables in `TOverrideStreamer`: `m_int` and `m_double`:

```{code-block} cpp
---
caption: `TOverrideStreamer.hh`
emphasize-lines: 11,12
---
#pragma once

#include <TObject.h>

class TOverrideStreamer : public TObject {
  public:
    TOverrideStreamer( int val = 0 )
        : TObject(), m_int( val ), m_double( (double)val * 3.14 ) {}

  private:
    int m_int{ 0 };
    double m_double{ 0.0 };

    ClassDef( TOverrideStreamer, 1 );
};
```

We add a mask in the `Streamer` method to demonstrate how to handle special logic in overridden `Streamer` methods:

```{code-block} cpp
---
caption: `TOverrideStreamer.cc`
emphasize-lines: 16-23, 31-32
---
#include <TBuffer.h>
#include <TObject.h>
#include <iostream>

#include "TOverrideStreamer.hh"

ClassImp( TOverrideStreamer );

void TOverrideStreamer::Streamer( TBuffer& b ) {
    if ( b.IsReading() )
    {
        TObject::Streamer( b ); // Call base class Streamer

        b >> m_int;

        unsigned int mask;
        b >> mask; // We additionally read a mask
        if ( mask != 0x12345678 )
        {
            std::cerr << "Error: Unexpected mask value: " << std::hex << mask << std::dec
                      << std::endl;
            return;
        }

        b >> m_double;
    }
    else
    {
        TObject::Streamer( b ); // Call base class Streamer
        b << m_int;
        unsigned int mask = 0x12345678; // Example mask
        b << mask;                      // Write the mask
        b << m_double;
    }
}
```

## Step 1: Check the binary data

Before implementing the Reader and Factory, we should check the binary data of `TOverrideStreamer` to understand how the data is stored in the ROOT file:

```python
>>> import uproot
>>> import uproot_custom as uc
>>>
>>> br = uproot.open("demo_data.root")["my_tree:override_streamer"]
>>> bin_arr = br.array(interpretation=uc.AsBinary())
>>> evt0 = bin_arr[0].to_numpy()
>>> evt0
array([  0,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
         0,  18,  52,  86, 120,   0,   0,   0,   0,   0,   0,   0,   0],
      dtype=uint8)
```

Referring to the `Streamer` method above, we can see that the binary data contains:

- `TObject` content (10 bytes, `0,   1,   0,   0,   0,   0,   0,   0,   0,   0`)
- `m_int` (4 bytes, `0,   0,   0,   0`, which is 0)
- mask (4 bytes, `18,  52,  86, 120`, which is `0x12345678`)
- `m_double` (8 bytes, `0,   0,   0,   0,   0,   0,   0,   0`, which is 0.0)

These bytes are the data your Reader needs to read.

## Step 2: Implement Python Reader to read binary data

We implement a Python Reader named `OverrideStreamerReader`:

```{code-block} python
---
lineno-start: 1
emphasize-lines: 11-25
---
from array import array
import numpy as np

from uproot_custom.readers.python import IReader


class OverrideStreamerReader(IReader):
    def __init__(self, name):
        super().__init__(name)
        self.m_ints = array("i")       # int32
        self.m_doubles = array("d")    # float64

    def read(self, buffer):
        # Skip TObject header
        buffer.skip_TObject()

        # Read integer value
        self.m_ints.append(buffer.read_int32())

        # Read a custom added mask value
        mask = buffer.read_uint32()
        if mask != 0x12345678:
            raise RuntimeError(f"Error: Unexpected mask value: {mask:#x}")

        # Read double value
        self.m_doubles.append(buffer.read_double())

    def data(self):
        int_array = np.frombuffer(self.m_ints.tobytes(), dtype="i4")
        double_array = np.frombuffer(self.m_doubles.tobytes(), dtype="f8")
        return int_array, double_array
```

- In the `read` method, we skip the `TObject` header, then read the member variables and the mask according to the logic in the `Streamer` method.

(override-streamer-2-np)=
- In the `data` method, we return a tuple containing 2 `numpy` arrays: one for `m_int` and the other for `m_double`.

## Step 3: Implement Python Factory

To use our `OverrideStreamerReader` and reconstruct the final `awkward` array, we need to implement a corresponding Factory. We can implement a Factory named `OverrideStreamerFactory` to do this.

A Factory requires at least 3 methods: `build_factory`, `build_python_reader` and `make_awkward_content`. An optional method `make_awkward_form` can be implemented to enable `dask` functionality.

First, import necessary modules:

```python
import awkward.contents
import awkward.forms
from uproot_custom import Factory
```

### Implement `build_factory`

We can make an assumpion that the `fName` of the `TStreamerInfo` is `TOverrideStreamer` for our class. If the `fName` matches, we return a tree config dictionary containing the Factory and the `name` of the corresponding Reader. Otherwise, we return `None` to let other factories have a chance to handle current class.

```python
class OverrideStreamerFactory(Factory):
    @classmethod
    def build_factory(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ):
        fName = cur_streamer_info["fName"]
        if fName != "TOverrideStreamer":
            return None

        return cls(fName) # Factory takes `name: str` as constructor argument
```

````{tip}
In production, you may want use `item_path` to make a more accurate identification of whether the current class is the one you want to handle:

```python
class OverrideStreamerFactory(Factory):
    @classmethod
    def build_factory(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ):
        if item_path != "/my_tree:override_streamer":
            return None

        return cls(fName)
```
````

### Implement `build_python_reader`

Implement `build_python_reader` to create an instance of `OverrideStreamerReader`:

```python
def build_python_reader(self):
    return OverrideStreamerReader(self.name)
```

### Implement `make_awkward_content`

Implement `make_awkward_content` to construct `awkward` contents from the raw data returned by the Reader:

```python
def make_awkward_content(self, raw_data):
    int_array, double_array = raw_data

    return awkward.contents.RecordArray(
        [
            awkward.contents.NumpyArray(int_array),
            awkward.contents.NumpyArray(double_array),
        ],
        ["m_int", "m_double"],
    )
```

The `raw_data` is the object returned by the `data` method of the Reader. In our example, it is a tuple containing 2 `numpy` arrays, as illustrated [above](override-streamer-2-np).

```{seealso}
Refer to [`awkward` direct constructors](https://awkward-array.org/doc/main/user-guide/how-to-create-constructors.html) for more details about `awkward` contents.
```

### (Optional) Implement `make_awkward_form`

The `make_awkward_form` method is optional, but it is easy to implement, since the `awkward.forms` is similar to `awkward.contents`:

```python
def make_awkward_form(self):
    return awkward.forms.RecordForm(
        [
            awkward.forms.NumpyForm("int32"),
            awkward.forms.NumpyForm("float64"),
        ],
        ["m_int", "m_double"],
    )
```

```{seealso}
Refer to [awkward forms](https://awkward-array.org/doc/main/reference/generated/ak.forms.Form.html) for more details about `awkward` forms.
```

## Step 4: Register target branch and the Factory

Finally, we need to register the branch we want to read with uproot-custom, and also register the `OverrideStreamerFactory` so that it can be used by uproot-custom.

We can do this by adding the following code in the `__init__.py` of your package:

```python
from uproot_custom import registered_factories, AsCustom

AsCustom.target_branches |= {
    "/my_tree:override_streamer",
}

registered_factories.add(OverrideStreamerFactory)
```

Don't forget to switch to the Python backend during development, since the
default backend is C++:

```python
import uproot_custom.factories as fac
fac.reader_backend = "python"  # default is "cpp"
```

## Step 5: Read data with Uproot

Now we can read the data using Uproot as usual:

```python
>>> b = uproot.open("demo_data.root")["my_tree:override_streamer"]
>>> arr = b.array()
```

## Step 6: Port the reader to C++ for production speed

Once the Python reader is working, you can port the same logic to C++ for
significantly better performance. **The C++ reader only needs to keep the same
reading logic as the Python version** — the same fields read in the same
order, and `data()` returning the same structure.

```{seealso}
See [](../../tutorial/customize-factory-reader/port-to-cpp.md) for the full
C++ reader API reference (IReader, BinaryBuffer, pybind11 bindings).
```

```{code-block} cpp
---
caption: "`OverrideStreamerReader` (C++) — same logic as the Python version"
lineno-start: 1
emphasize-lines: 16-33
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

    void read( BinaryBuffer& buffer ) {
        // Skip TObject header
        buffer.skip_TObject();

        // Read integer value
        m_data_ints->push_back( buffer.read<int>() );

        // Read a custom added mask value
        auto mask = buffer.read<uint32_t>();
        if ( mask != 0x12345678 )
        {
            throw std::runtime_error( "Error: Unexpected mask value: " +
                                      std::to_string( mask ) );
        }

        // Read double value
        m_data_doubles->push_back( buffer.read<double>() );
    }

    py::object data() const {
        auto int_array    = make_array( m_data_ints );
        auto double_array = make_array( m_data_doubles );
        return py::make_tuple( int_array, double_array );
    }

  private:
    const std::string m_name;
    std::shared_ptr<std::vector<int>> m_data_ints;
    std::shared_ptr<std::vector<double>> m_data_doubles;
};

// Declare the reader
PYBIND11_MODULE( my_reader_cpp, m ) {
    declare_reader<OverrideStreamerReader, std::string>( m, "OverrideStreamerReader" );
}
```

Then add `build_cpp_reader` to the factory:

```python
from .my_reader_cpp import OverrideStreamerReader as OverrideStreamerCppReader

def build_cpp_reader(self):
    return OverrideStreamerCppReader(self.name)
```

After adding `build_cpp_reader`, simply remove the
`fac.reader_backend = "python"` line (or set it back to `"cpp"`) to use the
default C++ backend for production:

```python
import uproot_custom.factories as fac
fac.reader_backend = "cpp"  # this is the default, so you can also just remove the line
```
```

The factory's `make_awkward_content` and `make_awkward_form` remain exactly
the same — they work identically regardless of which backend is used,
because both readers return data in the same structure.
