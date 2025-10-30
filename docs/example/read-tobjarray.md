# Example 2: Read `TObjArray` with unique known type

```{seealso}
A full example can be found in the `example` directory of [this repo](https://github.com/mrzimu/uproot-custom/tree/main/example).
```

This example shows how to use user-known rules to read data.

In this example, we define a `TObjWithObjArray` class, which contains a `TObjArray` of `TObjWithInt` objects. We know the type of objects in the `TObjArray` is always `TObjWithInt`, so we can use user-known rules to read the data.

The definition of `TObjInObjArray` and `TObjWithObjArray` is as follows:

```{code-block} cpp
---
caption: Definition of `TObjInObjArray`
---
class TObjInObjArray : public TObject {
  private:
    // STL
    std::string m_str;
    std::vector<int> m_vec_int;
    std::map<int, float> m_map_if;
    std::map<std::string, double> m_map_sd;
    std::map<int, std::string> m_map_is;
    std::map<int, std::vector<int>> m_map_vec_int;
    std::map<int, std::map<int, float>> m_map_map_if;

    // TArray
    TArrayI m_tarr_i{ 0 };
    TArrayC m_tarr_c{ 0 };
    TArrayS m_tarr_s{ 0 };
    TArrayL m_tarr_l{ 0 };
    TArrayF m_tarr_f{ 0 };
    TArrayD m_tarr_d{ 0 };

    // TString
    TString m_tstr;

    // CStyle array
    int m_carr_int[3]{ 0, 0, 0 };
    std::vector<int> m_carr_vec_int[2];

    // basic types
    bool m_bool{ false };
    int8_t m_int8{ 0 };
    int16_t m_int16{ 0 };
    int32_t m_int32{ 0 };
    int64_t m_int64{ 0 };
    uint8_t m_uint8{ 0 };
    uint16_t m_uint16{ 0 };
    uint32_t m_uint32{ 0 };
    uint64_t m_uint64{ 0 };
    float m_float{ 0.0 };
    double m_double{ 0.0 };

    ClassDef( TObjInObjArray, 1 );

  public:
    // ... (skipped for brevity)
};
```

```{code-block} cpp
---
caption: Definition of `TObjWithObjArray`
---
class TObjWithObjArray : public TObject {
  private:
    TObjArray m_obj_array;

    ClassDef( TObjWithObjArray, 1 );

  public:
    TObjWithObjArray( int val = 0 ) : TObject(), m_obj_array()
    {
        // preallocate space for 5 elements
        for ( int i = 0; i < val % 5; i++ )
        {
            // This will lead to memory leak, but it's just an example.
            m_obj_array.Add( new TObjInObjArray( val + i ) );
        }
    }
};
```

## Step 1: Check binary data

Similar to [Example 1](override-streamer.md), we should check the binary data first. Since `ROOT` automatically splits `TObjWithObjArray` into several sub-branches, we can just focus on the branch `m_obj_array`.

To print the binary data, run:

```python
>>> import uproot
>>> import uproot_custom as uc
>>>
>>> br = uproot.open("demo_data.root")["my_tree:obj_with_obj_array/m_obj_array"]
>>> bin_arr = br.array(interpretation=uc.AsBinary())
>>> evt1 = bin_arr[1].to_numpy()
>>> evt1
array([ 64,   0,   1, 155,   0,   3,   0,   1,   0,   0,   0,   0,   0,
         0,   0,   0,   0,   0,   0,   0,   1,   0,   0,   0,   0,  64,
         0,   1, 130, 255, 255, 255, 255,  84,  79,  98, 106,  73, 110,
        79,  98, 106,  65, 114, 114,  97, 121,   0,  64,   0,   1, 107,
         0,   1,   0,   1,   0,   0,   0,   0,   0,   0,   0,   0,  64,
         0,   0,   8,   0,   9,   5, 115, 116, 114,  95,  49,  64,   0,
         0,  10,   0,   9,   0,   0,   0,   1,   0,   0,   0,   1,  64,
         0,   0,  20,  64,   9,   0,   0, 105,   3,  41, 120,   0,   0,
         0,   1,   0,   0,   0,   0,  63, 128,   0,   0,  64,   0,   0,
        32,  64,   9,   0,   0, 250, 148,  40, 178,   0,   0,   0,   1,
        64,   0,   0,   8,   0,   9,   5, 107, 101, 121,  95,  48,  63,
       240,   0,   0,   0,   0,   0,   0,  64,   0,   0,  28,  64,   9,
         0,   0,  11,  95, 183,  82,   0,   0,   0,   1,   0,   0,   0,
         0,  64,   0,   0,   8,   0,   9,   5, 118,  97, 108,  95,  49,
        64,   0,   0,  34,  64,   9,   0,   0,  11,  95, 183,  82,   0,
         0,   0,   1,   0,   0,   0,   0,  64,   0,   0,  14,   0,   9,
         0,   0,   0,   2,   0,   0,   0,   1,   0,   0,   0,  11,  64,
         0,   0,  48,  64,   9,   0,   0,  11,  95, 183,  82,   0,   0,
         0,   1,   0,   0,   0,   0,  64,   0,   0,  28,  64,   9,   0,
         0, 105,   3,  41, 120,   0,   0,   0,   2,   0,   0,   0,   0,
         0,   0,   0,  10,  63, 128,   0,   0,  64,   0,   0,   0,   0,
         0,   0,   1,   0,   0,   0,   1,   0,   0,   0,   1,   1,   0,
         0,   0,   1,   0,   1,   0,   0,   0,   1,   0,   0,   0,   0,
         0,   0,   0,   1,   0,   0,   0,   1,  63, 128,   0,   0,   0,
         0,   0,   1,  63, 240,   0,   0,   0,   0,   0,   0,   6, 116,
       115, 116, 114,  95,  49,   0,   0,   0,   1,   0,   0,   0,   2,
         0,   0,   0,   3,  64,   0,   0,  26,   0,   9,   0,   0,   0,
         2,   0,   0,   0,   1,   0,   0,   0,  11,   0,   0,   0,   2,
         0,   0,   0,   2,   0,   0,   0,  12,   0,   1,   0,   2,   0,
         0,   0,   3,   0,   0,   0,   0,   0,   0,   0,   4,  11,   0,
        12,   0,   0,   0,  13,   0,   0,   0,   0,   0,   0,   0,  14,
        63, 140, 204, 205,  64,   1, 153, 153, 153, 153, 153, 154],
      dtype=uint8)
```

We can refer to the `TObjArray::Streamer` method:

```{code-block} cpp
---
caption: `TObjArray::Streamer` method
lineno-start: 1
---
void TObjArray::Streamer(TBuffer &b)
{
   UInt_t R__s, R__c;
   Int_t nobjects;
   if (b.IsReading()) {
      Version_t v = b.ReadVersion(&R__s, &R__c);
      if (v > 2)
         TObject::Streamer(b);
      if (v > 1)
         fName.Streamer(b);

      if (GetEntriesFast() > 0) Clear();

      b >> nobjects;
      b >> fLowerBound;
      if (nobjects >= fSize) Expand(nobjects);
      fLast = -1;
      TObject *obj;
      for (Int_t i = 0; i < nobjects; i++) {
         obj = (TObject*) b.ReadObjectAny(TObject::Class());
         if (obj) {
            fCont[i] = obj;
            fLast = i;
         }
      }
      Changed();
      b.CheckByteCount(R__s, R__c,TObjArray::IsA());
   } else {
      // skipped the writing part for brevity
   }
}
```

According to the `Streamer` method, the binary data contains:

1. `Line 6`: The first 6 bytes are the `fNBytes`(uint32) +`fVersion(int16)` header ([refer to here](nbytes-version-header)).

2. `Line 7-8`: Since the `fVersion` is `3` > `2`, the base class `TObject` is then streamed, which [takes 10 bytes](https://root.cern/doc/v636/tobject.html).

3. `Line 9-10`: Since the `fVersion` is `3` > `1`, the next part is `fName` (`TString`).

3. `Line 14`: The next 4 bytes is `nobjects` (int32), which is `[0, 0, 0, 1]`, i.e. `1`. This means there is one object in this `TObjArray`.

4. `Line 15`: The next 4 bytes is `fLowerBound` (int32), which is `[0, 0, 0, 0]`, i.e. `0`.

5. `Line 19-25`: Loop over `nobjects` to read each object. Note that the `[255, 255, 255, 255]` indicates that the object's binary layout follows [this rule](https://root.cern/doc/v636/dobject.html). In `uproot-custom`, it can be handled by `ObjectHeaderFactory`.

```{tip}
For other `ROOT` built-in classes, it is suggested to check both the streamer information and the source code. If the `Streamer` method is not overridden, the streamer information is usually enough.
```

In summary, the binary data contains:

- `TObjArray` header (`fNBytes`+`fVersion`+`TObject`+`fName`+`nobjects`+`fLowerBound`).
- Loop over `nobjects` to read each object:
    - `ObjectHeader` before each `TObjInObjArray` object.
    - Data members of `TObjInObjArray` object.

So we need such factories/readers to read the data:

- `TObjArrayFactory`/`TObjArrayReader` to read `TObjArray` header and loop over `nobjects`.
- `ObjectHeaderFactory`/`ObjectHeaderReader` to read `ObjectHeader`, which are already implemented in `uproot-custom`.
- `AnyClassFactory`/`AnyClassReader` to read `TObjInObjArray` object, which are already implemented in `uproot-custom`.

The `TObjArrayFactory`/`TObjArrayReader` should be implemented by ourselves. Note that since we know the type of objects in the `TObjArray` is always `TObjInObjArray`, we can take just 1 `AnyClassFactory`/`AnyClassReader` as sub-factory/sub-reader to read all objects. This is also a process that embedding user-known rules.

## Step 2: Implement C++ `reader` to read binary data

Our `TObjArrayReader` can be implemented as follows:

```{code-block} cpp
class TObjArrayReader : public IReader {
  private:
    SharedReader m_element_reader;
    std::shared_ptr<std::vector<int64_t>> m_offsets;

  public:
    TObjArrayReader( std::string name, SharedReader element_reader )
        : IReader( name )
        , m_element_reader( element_reader )
        , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) ) {}

    void read( BinaryBuffer& buffer ) override final {
        buffer.skip_fNBytes();
        buffer.skip_fVersion();
        buffer.skip_TObject();
        buffer.read_TString(); // fName
        auto fSize = buffer.read<uint32_t>();
        buffer.skip( 4 ); // fLowerBound

        m_offsets->push_back( m_offsets->back() + fSize );
        m_element_reader->read_many( buffer, fSize );
    }

    py::object data() const override final {
        auto offsets_array      = make_array( m_offsets );
        py::object element_data = m_element_reader->data();
        return py::make_tuple( offsets_array, element_data );
    }
};

PYBIND11_MODULE( my_reader_cpp, m ) {
    declare_reader<TObjArrayReader, std::string, SharedReader>( m, "TObjArrayReader" );
}
```

- In the constructor, we take one `SharedReader` as the `m_element_reader`, which is expected to read `TObjInObjArray` objects.

- In `read` method, we read the `TObjArray` header, then call `m_element_reader->read_many` to read multiple `TObjInObjArray` objects in one go. Also, we record the offsets of each event in `m_offsets`.

- In `data` method, we return a tuple of `(offsets, element_data)`, where `offsets` is a 1D array of int64, `element_data` is the data returned by `m_element_reader`.

- Finally, we declare the `TObjArrayReader` in the `my_reader_cpp` module.

```{important}
You should always use `IReader::read_many` method to read multiple objects in one go, since some classes (e.g. `std::vector`) may have "1 header + multiple objects" structure.
```

## Step 3: Implement Python `factory`

Similar to [Example 1](override-streamer.md), we need to identify the `TObjArray` branch and implement a corresponding `factory` to use our `TObjArrayReader`.

First, import necessary modules. Since we need to use `ObjectHeaderFactory` and `AnyClassFactory`, some extra imports are needed:

```python
import awkward.contents
import awkward.forms
import awkward.index

from uproot_custom import (
    Factory,
    build_factory,
)
from uproot_custom.factories import AnyClassFactory, ObjectHeaderFactory

from .my_reader_cpp import TObjArrayReader
```

The `my_reader_cpp` is the compiled C++ module containing our `TObjArrayReader`.

### Implement `build_factory`

In this example, we simply regard any `TObjArray` branch as our target branch. You can implement more specific rules to identify the target branch with `item_path`.

```{code-block} python
---
lineno-start: 1
emphasize-lines: 3-4, 18-19, 21-29, 31-40
---
class TObjArrayFactory(Factory):
    @classmethod
    def priority(cls):
        return 50

    @classmethod
    def build_factory(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ):
        if top_type_name != "TObjArray":
            return None

        item_path = item_path.replace(".TObjArray*", "")
        obj_typename = "TObjInObjArray"

        sub_factories = []
        for s in all_streamer_info[obj_typename]:
            sub_factories.append(
                build_factory(
                    cur_streamer_info=s,
                    all_streamer_info=all_streamer_info,
                    item_path=f"{item_path}.{obj_typename}",
                )
            )

        return cls(
            name=cur_streamer_info["fName"],
            element_factory=ObjectHeaderFactory(
                name=obj_typename,
                element_factory=AnyClassFactory(
                    name=obj_typename,
                    sub_factories=sub_factories,
                ),
            ),
        )
```

- `Line 3-4`: Override `priority` method to give a higher priority than the factories with default priority `10`, so that our factory can be chosen first.

- `Line 18-19`: Fix the `item_path`, otherwise the `.TObjArray*` suffix will be kept to the final awkward arrays.

- `Line 21-29`: Prepare the `sub_configs` for `AnyClassFactory` to read `TObjInObjArray` objects.

- `Line 31-40`: Combine `ObjectHeaderFactory` and `AnyClassFactory` as the `element_config` to read each object in the `TObjArray`.

### Implement constructor

The `TObjArrayFactory` requires an `element_factory` to read each object in the `TObjArray`. So we need to implement the constructor:

```python
def __init__(self, name: str, element_factory: Factory):
    super().__init__(name)
    self.element_factory = element_factory
```

### Implement `build_cpp_reader`

The `build_cpp_reader` method is straightforward:

```{code-block} python
---
lineno-start: 1
emphasize-lines: 2
---
def build_cpp_reader(self):
    element_reader = self.element_factory.build_cpp_reader()
    return TObjArrayReader(self.name, element_reader)
```

- In `Line 2`, we use `self.element_factory.build_cpp_reader` to create the `element_reader`. Here, `ObjectHeaderFactory`, then `AnyClassFactory` are called to create corresponding sub-factories.

- In `Line 3`, we just create an instance of `TObjArrayReader`, passing the `element_reader` to it.

### Implement `make_awkward_content`

The `make_awkward_content` method is also straightforward:

```{code-block} python
def make_awkward_content(self, raw_data):
    offsets, element_raw_data = raw_data
    element_content = self.element_factory.make_awkward_content(element_raw_data)
    return awkward.contents.ListOffsetArray(
        awkward.index.Index64(offsets),
        element_content,
    )
```

We use `self.element_factory.make_awkward_content` to construct the `element_content`, then combine it with `offsets` to create a `ListOffsetArray`.

### (Optional) Implement `make_awkward_form`

You can implement `make_awkward_form` to provide the `awkward` form of the final array without reading the binary data:

```{code-block} python
def make_awkward_form(self):
    element_form = self.element_factory.make_awkward_form()
    return awkward.forms.ListOffsetForm(
        "i64",
        element_form,
    )
```

## Step 4: Register target branch and the `factory`

Finally, register the branch we want to read with `uproot-custom`, and also register the `TObjArrayFactory` so that it can be used by `uproot-custom`. 

We can do this by adding the following code in the `__init__.py` of your package:

```python
from uproot_custom import registered_factories, AsCustom

AsCustom.target_branches |= {
    "/my_tree:obj_with_obj_array/m_obj_array",
}

registered_factories.add(TObjArrayFactory)
```

## Step 5: Read data with `uproot`

Now we can read the data using `uproot` as usual:

```python
>>> b = uproot.open("demo_data.root")["my_tree:obj_with_obj_array/m_obj_array"]
>>> arr = b.array()
```
