# Example 1: `Streamer` method is overridden

Goal: handle a class whose `Streamer` overrides the default layout by inserting
an extra mask. We will inspect the bytes, write a C++ reader, wrap it with a
factory, register it, then read with Uproot.

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

Before implementing the `reader` and `factory`, we should check the binary data of `TOverrideStreamer` to understand how the data is stored in the ROOT file:

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

These bytes are the data your `reader` needs to read.

## Step 2: Implement C++ `reader` to read binary data

We can implement a `reader` named `OverrideStreamerReader` to do this:

```{code-block} cpp
---
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

- In the `read` method, we skip the `TObject` header, then read the member variables and the mask according to the logic in the `Streamer` method.

(override-streamer-2-np)=
- In the `data` method, we return a `py::tuple` containing 2 `numpy` arrays: one for `m_int` and the other for `m_double`.

- Finally we declare the `reader` in the `PYBIND11_MODULE`, so that it can be used in Python.

## Step 3: Implement Python `factory`

To use our `OverrideStreamerReader` and reconstruct the final `awkward` array, we need to implement a corresponding `factory`. We can implement a `factory` named `OverrideStreamerFactory` to do this.

A `factory` requires at least 3 methods: `build_factory`, `build_cpp_reader` and `make_awkward_content`. An optional method `make_awkward_form` can be implemented to enable `dask` functionality.

First, import necessary modules:

```python
import awkward.contents
import awkward.forms
from uproot_custom import Factory
from .my_reader_cpp import OverrideStreamerReader
```

The `my_reader_cpp` is the compiled C++ module containing our `OverrideStreamerReader`.

### Implement `build_factory`

We can make an assumpion that the `fName` of the `TStreamerInfo` is `TOverrideStreamer` for our class. If the `fName` matches, we return a tree config dictionary containing the `factory` and the `name` of the corresponding `reader`. Otherwise, we return `None` to let other factories have a chance to handle current class.

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

### Implement `build_cpp_reader`

Implement `build_cpp_reader` to create an instance of `OverrideStreamerReader`:

```python
def build_cpp_reader(self):
    return OverrideStreamerReader(self.name)
```

### Implement `make_awkward_content`

Implement `make_awkward_content` to construct `awkward` contents from the raw data returned by the `reader`:

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

The `raw_data` is the object returned by the `data` method of the `reader`. In our example, it is a `py::tuple` containing 2 `numpy` arrays, as illustrated [above](override-streamer-2-np).

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

## Step 4: Register target branch and the `factory`

Finally, we need to register the branch we want to read with uproot-custom, and also register the `OverrideStreamerFactory` so that it can be used by uproot-custom.

We can do this by adding the following code in the `__init__.py` of your package:

```python
from uproot_custom import registered_factories, AsCustom

AsCustom.target_branches |= {
    "/my_tree:override_streamer",
}

registered_factories.add(OverrideStreamerFactory)
```

## Step 5: Read data with Uproot

Now we can read the data using Uproot as usual:

```python
>>> b = uproot.open("demo_data.root")["my_tree:override_streamer"]
>>> arr = b.array()
```
