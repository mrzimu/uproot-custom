# Example 1: `Streamer` method is overridden

Goal: handle a class whose `Streamer` overrides the default layout by inserting an extra mask. We inspect the bytes, write a **Detree reader**, wrap it with a factory, register it, and read with Uproot. The [Python + C++ route](#override-streamer-cpp-route) then shows the same reader written as a Python `IReader` and ported to C++.

```{seealso}
A full example can be found in the [example repository](https://github.com/mrzimu/uproot-custom-example).
```

We define a demo class `TOverrideStreamer` whose `Streamer` method is overridden to show how to read such classes using Uproot-custom.

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
>>> from uproot.interpretation.custom import AsBinary
>>>
>>> br = uproot.open("demo_data.root")["my_tree:override_streamer"]
>>> bin_arr = br.array(interpretation=AsBinary())
>>> evt0 = bin_arr[0].to_numpy()
>>> evt0
array([  0,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
         0,  18,  52,  86, 120,   0,   0,   0,   0,   0,   0,   0,   0],
      dtype=uint8)
```

`demo_data.root` is `tests/demo-data.root` of the [example repository](https://github.com/mrzimu/uproot-custom-example); copy it next to your script, or point the code at your own file.

Referring to the `Streamer` method above, we can see that the binary data contains:

- `TObject` content (10 bytes, `0,   1,   0,   0,   0,   0,   0,   0,   0,   0`)
- `m_int` (4 bytes, `0,   0,   0,   0`, which is 0)
- mask (4 bytes, `18,  52,  86, 120`, which is `0x12345678`)
- `m_double` (8 bytes, `0,   0,   0,   0,   0,   0,   0,   0`, which is 0.0)

These bytes are the data your Reader needs to read.

## Step 2: Implement the Detree reader

We implement a Detree reader named `OverrideStreamerReader`:

```{code-block} python
---
lineno-start: 1
emphasize-lines: 9-12
---
import numpy as np

from uproot_custom.detree import Buffer, Reader, reader


@reader
class OverrideStreamerReader(Reader):
    m_ints = Buffer("i")      # int32
    m_doubles = Buffer("d")   # float64

    def read(self, stream):
        # Skip TObject header
        stream.skip_TObject()

        # Read integer value
        self.m_ints.append(stream.read_int32())

        # Read a custom added mask value
        mask = stream.read_uint32()
        assert mask == 0x12345678, "unexpected mask value"

        # Read double value
        self.m_doubles.append(stream.read_double())

    def data(self):
        return np.asarray(self.m_ints), np.asarray(self.m_doubles)
```

- The class declares its two output buffers as fields; `read` is compiled to a detree-vm module and runs inside the machine.
- `read` skips the `TObject` header, then reads the members and the mask in the order the `Streamer` method writes them. `assert` replaces the `raise` — it is the only failure mode the compiler accepts.
- `data` is ordinary Python and returns the two arrays in the shape the factory expects.

(override-streamer-2-np)=

## Step 3: Implement the factory

To use our `OverrideStreamerReader` and reconstruct the final `awkward` array, we need to implement a corresponding Factory. We can implement a Factory named `OverrideStreamerFactory` to do this.

A Factory requires at least 3 methods: `build_factory`, `build_detree_reader` and `make_awkward_content`. An optional method `make_awkward_form` can be implemented to enable lazy evaluation functionality.

First, import necessary modules:

```python
import awkward.contents
import awkward.forms
from uproot_custom import Factory
```

### Implement `build_factory`

The class name arrives as `top_type_name` (with `std::` stripped), so that is what the match tests. `cur_streamer_info["fName"]` is the *member* name, which equals the class name only when the class is stored as the whole branch — here it is, but a factory that also has to catch the class as a member of a split tree must not rely on that. [Write a Detree reader](../tutorial/write-a-reader.md) has the field-by-field table under `build_factory`.

If the match succeeds, we return an instance carrying the node's name; otherwise `None` lets the next registered factory try.

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
        if top_type_name != "TOverrideStreamer":
            return None

        return cls(cur_streamer_info["fName"])  # Factory takes `name: str`
```

````{tip}
In production, you may want to use `item_path` to make a more accurate identification of whether the current class is the one you want to handle:

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

        return cls(cur_streamer_info["fName"])
```

`item_path` starts as the branch's regularized object-path and grows by `.<member>` for every level below it, so it identifies a node by position rather than by type.
````

### Implement `build_detree_reader`

Implement `build_detree_reader` to create an instance of `OverrideStreamerReader`:

```python
def build_detree_reader(self):
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

The `raw_data` is the object returned by the `data` method of the Reader. In our example, it is a tuple containing two `numpy` arrays, as illustrated [above](override-streamer-2-np).

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

This will be used when users try to access the array lazily, e.g. using `uproot.dask` or `b.array(virtual=True)`.

```{seealso}
Refer to [awkward forms](https://awkward-array.org/doc/main/reference/generated/ak.forms.Form.html) for more details about `awkward` forms.
```

## Step 4: Register target branch and the Factory

Finally, we need to register the branch we want to read with Uproot-custom, and also register the `OverrideStreamerFactory` so that it can be used by Uproot-custom.

We can do this by adding the following code in the `__init__.py` of your package:

```python
from uproot_custom import claim, registered_factories

claim("/my_tree:override_streamer")

registered_factories.add(OverrideStreamerFactory)
```

Here the class is the whole branch, so the path names the branch itself. When the class sits inside a split tree — the more common layout — the path names the member that stores it, `/my_tree:override_streamer/m_obj`, and the factory must match on `top_type_name` because `cur_streamer_info["fName"]` is then `m_obj`. The path must be registered before the branch's interpretation is first computed; see [get started](../getting-started.md#step-2-register-the-branch).

The code default backend is `cpp`, so select Detree next to the registration, when your package is imported:

```python
import uproot_custom as uc
uc.set_backend("detree")  # the default is "cpp"
```

## Step 5: Read data with Uproot

Now we can read the data using Uproot as usual:

```python
>>> b = uproot.open("demo_data.root")["my_tree:override_streamer"]
>>> arr = b.array()
```

(override-streamer-cpp-route)=
## The Python + C++ route for the same class

The same class can also be read on the Python + C++ route. The factory and the `data` shape stay the same; the reader is written twice, and the factory gains one method per stage.

`````{tab-set}

````{tab-item} Python reader
```{code-block} python
---
caption: "`OverrideStreamerReader` (Python)"
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
        stream.skip_TObject()
        self.m_ints.append(stream.read_int32())

        mask = stream.read_uint32()
        if mask != 0x12345678:
            raise RuntimeError(f"Error: Unexpected mask value: {mask:#x}")

        self.m_doubles.append(stream.read_double())

    def data(self):
        return np.asarray(self.m_ints), np.asarray(self.m_doubles)
```

The Python reader is ordinary Python, so the mask check can `raise`. See [stage 1 of the route](../advanced/python-reader.md).
````

````{tab-item} C++ reader
```{code-block} cpp
---
caption: "`OverrideStreamerReader` (C++)"
---
class OverrideStreamerReader : public IReader {
  public:
    OverrideStreamerReader( std::string name )
        : IReader( name )
        , m_ints( std::make_shared<std::vector<int32_t>>() )
        , m_doubles( std::make_shared<std::vector<double>>() ) {}

    void read( BinaryStream& stream ) {
        stream.skip_TObject();
        m_ints->push_back( stream.read<int32_t>() );

        auto mask = stream.read<uint32_t>();
        if ( mask != 0x12345678 )
            throw std::runtime_error( "Unexpected mask: " + std::to_string( mask ) );

        m_doubles->push_back( stream.read<double>() );
    }

    py::object data() const {
        return py::make_tuple( make_array( m_ints ), make_array( m_doubles ) );
    }

  private:
    std::shared_ptr<std::vector<int32_t>> m_ints;
    std::shared_ptr<std::vector<double>> m_doubles;
};

PYBIND11_MODULE( my_reader_cpp, m ) {
    declare_reader<OverrideStreamerReader, std::string>( m, "OverrideStreamerReader" );
}
```

The C++ reader runs fastest and costs the most to ship: it is built into a pybind11 extension that must be pinned and rebuilt. See [stage 2 of the route](../advanced/cpp-reader.md).
````
`````

Add the matching factory methods to make the backends selectable:

```python
class OverrideStreamerFactory(Factory):
    # ... build_factory, make_awkward_content, make_awkward_form ...

    def build_detree_reader(self):
        return OverrideStreamerReader(self.name)

    def build_python_reader(self):
        return OverrideStreamerPythonReader(self.name)

    def build_cpp_reader(self):
        return cpp.OverrideStreamerReader(self.name)
```

Only the selected backend's method is called, so the other two readers are simply unused.

```{note}
The external [example repository](https://github.com/mrzimu/uproot-custom-example) ships the Python and C++ implementations; the Detree version on this page is the same read path in the same project layout.
```
