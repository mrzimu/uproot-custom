# Bootstrapping custom-class reading in uproot-custom

Reading a `TBranch` with uproot-custom is a pipeline that turns ROOT streamer
metadata into `awkward` arrays. At a high level:

1. Uproot-custom reads the branch's streamer information (field names, types, and layout).
2. Factories recursively instantiate and connect themselves into a tree that mirrors the streamer hierarchy.
3. Factories recursively create and connect readers.
4. The composed reader graph pulls binary data from the buffer and returns raw results to the factories.
5. Factories recursively convert raw `numpy` arrays into `awkward` contents, then assemble the final `awkward` array.

## Build factory instances

When a branch is read, uproot-custom first builds a `factory` instance from the
class streamer information. That factory must also recursively build factories
for every data member.

For example, the streamer information of `TSimpleObject` is as follows (as illustrated in [streamer information](simple-obj-streamer-info)):

```python
{'@fUniqueID': 0,
 '@fBits': 16842752,
 'fName': 'TSimpleObject',
 'fTitle': '',
 'fCheckSum': 2574715488,
 'fClassVersion': 1,
 'fElements': <TObjArray of 9 items at 0x74083a583b90>}
```

The `AsCustom` interpretation calls `uproot_custom.factories.build_factory` to
construct the factory for `TSimpleObject`. `build_factory` loops over all
registered factories (highest priority first) and invokes each factory's
`build_factory` method. If a factory recognizes the current streamer
information, it returns an instance for this node; otherwise it returns `None`.

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

For `TSimpleObject`, `AnyClassFactory` can handle it. In `AnyClassFactory.build_factory` method, `AnyClassFactory` loops over the `fElements` attribute, and recursively calls `uproot_custom.factories.build_factory` method to generate the factory of each data member:

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

According to the [full streamer information of `TSimpleObject`'s data members](all-streamer-info-output), the final factory instance of `TSimpleObject` looks like this:

```python
{
    "factory": uproot_custom.factories.AnyClassFactory,
    "name": "TSimpleObject",
    "sub_factories": [
        {
            "factory": uproot_custom.factories.TObjectFactory,
            "name": "TObject",
            "keep_data": False,
        },
        {
            "factory": uproot_custom.factories.PrimitiveFactory,
            "name": "m_int",
            "ctype": "i4",
        },
        {
            "factory": uproot_custom.factories.STLStringFactory,
            "name": "m_str",
            "with_header": True,
        },
        {
            "factory": uproot_custom.factories.CStyleArrayFactory,
            "name": "m_arr_int",
            "element_factory": {
                "factory": uproot_custom.factories.PrimitiveFactory,
                "name": "m_arr_int",
                "ctype": "i4",
            },
            "flat_size": np.int64(5),
            "fMaxIndex": array([5, 0, 0, 0, 0], dtype=">i4"),
            "fArrayDim": 1,
        },
        {
            "factory": uproot_custom.factories.STLSeqFactory,
            "name": "m_vec_double",
            "with_header": True,
            "objwise_or_memberwise": -1,
            "element_factory": {
                "factory": uproot_custom.factories.PrimitiveFactory,
                "name": "m_vec_double",
                "ctype": "d",
            },
        },
        {
            "factory": uproot_custom.factories.STLMapFactory,
            "name": "m_map_int_double",
            "with_header": True,
            "objwise_or_memberwise": -1,
            "key_factory": {
                "factory": uproot_custom.factories.PrimitiveFactory,
                "name": "key",
                "ctype": "i4",
            },
            "val_factory": {
                "factory": uproot_custom.factories.PrimitiveFactory,
                "name": "val",
                "ctype": "d",
            },
        },
        {
            "factory": uproot_custom.factories.STLMapFactory,
            "name": "m_map_str_str",
            "with_header": True,
            "objwise_or_memberwise": -1,
            "key_factory": {
                "factory": uproot_custom.factories.STLStringFactory,
                "name": "key",
                "with_header": True,
            },
            "val_factory": {
                "factory": uproot_custom.factories.TStringFactory,
                "name": "val",
                "with_header": False,
            },
        },
        {
            "factory": uproot_custom.factories.TStringFactory,
            "name": "m_tstr",
            "with_header": False,
        },
        {
            "factory": uproot_custom.factories.TArrayFactory,
            "name": "m_tarr_int",
            "ctype": "i4",
        },
    ],
}
```

When `"factory"` is `STLSeqFactory` or `STLMapFactory`, the `"element_factory"` or
`"key_factory"`/`"val_factory"` fields point to the factory instances for the element,
key, and value types. Those are also generated by recursively calling
`uproot_custom.factories.build_factory`.

## Build C++ readers

Once the factory tree is built, `AsCustom` calls `Factory.build_cpp_reader` to
recursively construct C++ readers. The top-level factory delegates to its
sub-factories to build sub-readers, then combines them into the top-level
reader.

In `AnyClassFactory.build_cpp_reader` method, `AnyClassFactory` loops over the `sub_factories` attribute, and calls their `build_cpp_reader` method to build the C++ `reader` of each data member. Finally, it combines all sub-reader together to an `AnyClassReader`:

```{code-block} python
---
caption: Source code of `AnyClassFactory.build_cpp_reader`
emphasize-lines: 9
---
class AnyClassFactory(GroupFactory):
    ...

    def build_cpp_reader(self):
        sub_readers = [s.build_cpp_reader() for s in self.sub_factories]
        return uproot_custom.cpp.AnyClassReader(self.name, sub_readers)
```

## Read binary data with `reader`

Since the top-level reader can be combined with several sub-readers, it can of course drive sub-readers to do reading task. This is also done recursively:

```{code-block} cpp
---
caption: `AnyClassReader::read` method
emphasize-lines: 8
---
void read( BinaryBuffer& buffer ) override {
    auto fNBytes  = buffer.read_fNBytes();
    auto fVersion = buffer.read_fVersion();

    auto start_pos = buffer.get_cursor();
    auto end_pos   = buffer.get_cursor() + fNBytes - 2; // -2 for fVersion

    for ( auto& reader : m_element_readers ) reader->read( buffer );

    // ...
}
```

## Return results to Python

After reading completes, the top-level reader's `data` method returns the data
to Python. This is recursive: each reader pulls data from its sub-readers until
the leaf readers return `numpy` arrays. The top-level reader returns a nested
`tuple`/`list` of those arrays to Python.

The `data` method of `PrimitiveReader`, `STLSeqReader` and `AnyClassReader` are shown here as examples:

```{code-block} cpp
---
caption: `PrimitiveReader::data` method
---
py::object data() const override { return make_array( m_data ); }
```

```{code-block} cpp
---
caption: `STLSeqReader::data` method
---
py::object data() const override {
    auto offsets_array = make_array( m_offsets );
    auto elements_data = m_element_reader->data();
    return py::make_tuple( offsets_array, elements_data );
}
```

```{code-block} cpp
---
caption: `AnyClassReader::data` method
---
py::object data() const override {
    py::list res;
    for ( auto& reader : m_element_readers ) { res.append( reader->data() ); }
    return res;
}
```

## Make `awkward` content

With the (possibly nested) `numpy` arrays returned by the top-level reader, the
`AsCustom` interpretation calls `Factory.make_awkward_content` to reconstruct the
final `awkward` content.

Similar to the previous steps, the top-level factory extracts the raw arrays for
its sub-factories, calls their `make_awkward_content`, then combines the results
into the final `awkward` array:

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

Once the top-level factory returns the final `awkward` content, `AsCustom` builds
the `awkward` array and returns it to the user.

## Make `awkward` form

`awkward` form can be used in `dask`, enabling lazy evaluation and
out-of-core computation. The factory tree already describes the data structure,
so generating the `awkward` form is straightforward. It mirrors
`make_awkward_content` but does not require input data:

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
