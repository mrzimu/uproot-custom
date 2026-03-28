# Pipeline overview

This page explains the end-to-end pipeline that uproot-custom uses to turn
ROOT binary data into `awkward` arrays. Understanding this pipeline will help
you design your own factories and readers.

At a high level the pipeline has five stages:

1. **Build factories** — uproot-custom reads streamer information and
   recursively creates a tree of `Factory` instances that mirror the class
   hierarchy.
2. **Build readers** — each factory creates a corresponding `Reader` (Python
   or C++).
3. **Read binary data** — the composed reader graph walks the byte buffer.
4. **Return raw data** — leaf readers return `numpy` arrays; parent readers
   assemble them into nested tuples / lists.
5. **Build awkward arrays** — factories convert the raw arrays into
   `awkward` contents and form the final `awkward` array.

---

## Stage 1: Build factory instances

When a branch is read, `AsCustom` calls `uproot_custom.factories.build_factory`.
This function loops over all registered factory classes (highest priority first)
and invokes each one's `build_factory` class method. The first class that
returns a non-`None` instance wins.

```{code-block} python
---
caption: Source code of `uproot_custom.factories.build_factory`
emphasize-lines: 18-27
---
def build_factory(
    cur_streamer_info: dict,
    all_streamer_info: dict,
    item_path: str = "",
    **kwargs,
) -> "Factory":
    fName = cur_streamer_info["fName"]

    top_type_name = (
        get_top_type_name(cur_streamer_info["fTypeName"])
        if "fTypeName" in cur_streamer_info
        else None
    )

    if not kwargs.get("called_from_top", False):
        item_path = f"{item_path}.{fName}"

    for factory_class in sorted(registered_factories, key=lambda x: x.priority(), reverse=True):
        factory_instance = factory_class.build_factory(
            top_type_name,
            cur_streamer_info,
            all_streamer_info,
            item_path,
            **kwargs,
        )
        if factory_instance is not None:
            return factory_instance

    raise ValueError(f"Unknown type: {cur_streamer_info['fTypeName']} for {item_path}")
```

### Recursive factory construction

For composite classes such as `TSimpleObject`, `AnyClassFactory` matches and
then **recursively** calls `build_factory` for every data member listed in the
streamer information:

```{code-block} python
---
caption: Source code of `AnyClassFactory.build_factory`
emphasize-lines: 13-14
---
class AnyClassFactory(GroupFactory):
    ...

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        sub_streamers: list = all_streamer_info[top_type_name]
        sub_factories = [build_factory(s, all_streamer_info, item_path) for s in sub_streamers]
        return cls(name=top_type_name, sub_factories=sub_factories)
```

The resulting factory tree for `TSimpleObject`
(using the [streamer information](simple-obj-streamer-info) as input) looks
like this:

```python
{
    "factory": AnyClassFactory,
    "name": "TSimpleObject",
    "sub_factories": [
        {"factory": TObjectFactory,    "name": "TObject"},
        {"factory": PrimitiveFactory,  "name": "m_int",            "dtype": "int32"},
        {"factory": STLStringFactory,  "name": "m_str"},
        {"factory": CStyleArrayFactory,"name": "m_arr_int",        "flat_size": 5},
        {"factory": STLSeqFactory,     "name": "m_vec_double",     "element": "PrimitiveFactory(float64)"},
        {"factory": STLMapFactory,     "name": "m_map_int_double", "key/val": "Primitive/Primitive"},
        {"factory": STLMapFactory,     "name": "m_map_str_str",    "key/val": "STLString/TString"},
        {"factory": TStringFactory,    "name": "m_tstr"},
        {"factory": TArrayFactory,     "name": "m_tarr_int",       "dtype": "int32"},
    ],
}
```

---

## Stage 2: Build readers

Once the factory tree is ready, `AsCustom` calls `Factory.build_python_reader`
(or `Factory.build_cpp_reader` when using the default C++ backend) on the root
factory. Each factory delegates to its sub-factories to build sub-readers, then
combines them into a parent reader.

```{important}
The default reader backend is **C++** (`uproot_custom.factories.reader_backend = "cpp"`).
During development, you must explicitly switch to the Python backend:

    import uproot_custom.factories as fac
    fac.reader_backend = "python"
```

```{code-block} python
---
caption: Source code of `AnyClassFactory.build_python_reader`
emphasize-lines: 5-6
---
class AnyClassFactory(GroupFactory):
    ...

    def build_python_reader(self):
        sub_readers = [s.build_python_reader() for s in self.sub_factories]
        return uproot_custom.readers.python.AnyClassReader(self.name, sub_readers)
```

---

## Stage 3 & 4: Read binary data and return results

The top-level reader drives sub-readers recursively. For instance,
`AnyClassReader` reads its `fNBytes` + `fVersion` header, then asks each
sub-reader to consume its portion of the buffer:

```{code-block} python
---
caption: "`AnyClassReader.read` method (Python)"
emphasize-lines: 7
---
def read(self, buffer):
    fNBytes = buffer.read_fNBytes()
    start_pos = buffer.cursor
    end_pos = start_pos + fNBytes

    buffer.skip_fVersion()

    for reader in self.element_readers:
        reader.read(buffer)

    assert buffer.cursor == end_pos, (
        f"AnyClassReader({self.name}): Invalid read length!"
    )
```

After all entries are read, the top-level reader's `data()` method collects
results recursively — leaf readers return `numpy` arrays, and composite
readers assemble them into nested tuples or lists:

```{code-block} python
---
caption: "`PrimitiveReader.data` — leaf"
---
def data(self):
    return np.frombuffer(self._data.tobytes(), dtype=self.dtype)
```

```{code-block} python
---
caption: "`AnyClassReader.data` — composite"
---
def data(self):
    return [reader.data() for reader in self.element_readers]
```

---

## Stage 5: Build awkward arrays

With the nested arrays available in Python, `AsCustom` calls
`Factory.make_awkward_content` to reconstruct `awkward` contents. Each factory
extracts its slice of the raw data, delegates to sub-factories, then combines
the results:

```{code-block} python
---
caption: Source code of `GroupFactory.make_awkward_content`
---
class GroupFactory(Factory):
    ...

    def make_awkward_content(self, raw_data):
        sub_configs = self.sub_factories

        sub_fields = []
        sub_contents = []
        for s_fac, s_data in zip(sub_configs, raw_data):
            if isinstance(s_fac, TObjectFactory) and not s_fac.keep_data:
                continue

            sub_fields.append(s_fac.name)
            sub_contents.append(s_fac.make_awkward_content(s_data))

        return awkward.contents.RecordArray(sub_contents, sub_fields)
```

### Generating awkward forms

`awkward` forms describe the data structure without holding data, enabling
lazy evaluation with `dask`. Form generation mirrors `make_awkward_content` but
needs no input data:

```{code-block} python
---
caption: Source code of `GroupFactory.make_awkward_form`
---
class GroupFactory(Factory):
    ...

    def make_awkward_form(self):
        sub_configs = self.sub_factories

        sub_fields = []
        sub_contents = []
        for s_fac in sub_configs:
            if isinstance(s_fac, TObjectFactory) and not s_fac.keep_data:
                continue

            sub_fields.append(s_fac.name)
            sub_contents.append(s_fac.make_awkward_form())

        return ak.forms.RecordForm(sub_contents, sub_fields)
```

---

## Complete example: putting it all together

The five stages above may feel abstract. Below is a concrete, end-to-end
example that walks through every stage. We use a demo class
`TOverrideStreamer` that overrides the default ROOT `Streamer` method by
inserting an extra mask between its two data members.

```{code-block} cpp
---
caption: "Demo class — `TOverrideStreamer` (C++)"
---
class TOverrideStreamer : public TObject {
  private:
    int m_int{ 0 };
    double m_double{ 0.0 };

    ClassDef( TOverrideStreamer, 1 );
};
```

Its `Streamer` method is overridden to insert an extra mask (`0x12345678`)
between `m_int` and `m_double`:

```{code-block} cpp
---
caption: "Overridden `Streamer` method"
emphasize-lines: 7-8
---
void TOverrideStreamer::Streamer( TBuffer& b ) {
    if ( b.IsReading() ) {
        TObject::Streamer( b );
        b >> m_int;

        unsigned int mask;
        b >> mask; // additionally read a mask
        if ( mask != 0x12345678 ) { /* error */ }

        b >> m_double;
    } else {
        TObject::Streamer( b );
        b << m_int;
        unsigned int mask = 0x12345678;
        b << mask;
        b << m_double;
    }
}
```

Because of this override, the binary layout is:

| Content | Type | Size |
| ------- | ---- | ---- |
| `TObject` | — | 10 bytes |
| `m_int` | `int32_t` | 4 bytes |
| *mask* | `uint32_t` | 4 bytes |
| `m_double` | `double` | 8 bytes |

The built-in reader cannot handle the extra mask, so we must implement a
custom reader and factory.

### Stage 1 — Factory

The factory must implement four methods. `build_factory` matches on the
class name and returns an instance; the remaining methods build readers and
convert raw data to `awkward` arrays.

```{code-block} python
---
caption: "`OverrideStreamerFactory` — complete factory implementation"
lineno-start: 1
---
import awkward
import awkward.contents
import awkward.forms
from uproot_custom import Factory


class OverrideStreamerFactory(Factory):
    @classmethod
    def build_factory(cls, top_type_name, cur_streamer_info,
                      all_streamer_info, item_path, **kwargs):
        if cur_streamer_info["fName"] != "TOverrideStreamer":
            return None
        return cls(cur_streamer_info["fName"])

    def build_python_reader(self):
        # Stage 2 — create the reader
        return OverrideStreamerReader(self.name)

    def make_awkward_content(self, raw_data):
        # Stage 5a — convert raw numpy arrays to awkward content
        int_array, double_array = raw_data
        return awkward.contents.RecordArray(
            [awkward.contents.NumpyArray(int_array),
             awkward.contents.NumpyArray(double_array)],
            ["m_int", "m_double"],
        )

    def make_awkward_form(self):
        # Stage 5b — describe the data layout for dask
        return awkward.forms.RecordForm(
            [awkward.forms.NumpyForm("int32"),
             awkward.forms.NumpyForm("float64")],
            ["m_int", "m_double"],
        )
```

### Stage 2 — Reader

The reader implements the binary decoding logic. It reads every entry from
the byte buffer and accumulates values in Python `array` objects, then
returns them as `numpy` arrays.

```{code-block} python
---
caption: "`OverrideStreamerReader` — Python reader"
lineno-start: 1
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
        # Stage 3 — read binary data
        buffer.skip_TObject()                        # skip base class
        self.m_ints.append(buffer.read_int32())      # m_int

        mask = buffer.read_uint32()                  # custom mask
        if mask != 0x12345678:
            raise RuntimeError(f"Unexpected mask: {mask:#x}")

        self.m_doubles.append(buffer.read_double())  # m_double

    def data(self):
        # Stage 4 — return raw numpy arrays
        return np.asarray(self.m_ints), np.asarray(self.m_doubles)
```

### Register and read

With the factory and reader defined, register them and read data with Uproot:

```{code-block} python
---
caption: "Registration and usage"
lineno-start: 1
---
import uproot
import uproot_custom
import uproot_custom.factories as fac

# During development, use the Python backend
fac.reader_backend = "python"

# Register the target branch and the custom factory
uproot_custom.AsCustom.target_branches |= {
    "/my_tree:override_streamer",
}
uproot_custom.registered_factories.add(OverrideStreamerFactory)

# Read the data — Uproot will automatically invoke our factory/reader
arr = uproot.open("demo_data.root")["my_tree:override_streamer"].array()
arr.m_int    # <Array [0, 1, 2, ...] type='100 * int32'>
arr.m_double # <Array [0.0, 3.14, 6.28, ...] type='100 * float64'>
```

```{tip}
In a real project, put the factory, reader, and registration code inside a
Python package (see [](project-setup.md)). The registration is typically
done in the package's `__init__.py` so that it happens automatically on
import.
```

```{seealso}
For a full walkthrough — including binary-data inspection and porting to C++
— see [Example 1: Streamer method is overridden](../../example/override-streamer.md).
```

---

```{admonition} Next step
---
class: hint
---
Now that you understand the pipeline, move on to
[Investigate your data](investigate-data.md) to learn how to inspect
streamer information and raw binary bytes for the class you need to read.
```
