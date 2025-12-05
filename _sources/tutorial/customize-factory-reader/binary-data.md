# Binary data

Now let's turn to the binary data stored in file. Before starting to implement your own `reader`/`factory`, you need to check the raw binary data. As long as you understand how `ROOT` stores the binary data, you can implement your own `reader`/`factory` easily.

## Object splitting

Most of the time, data members are splitted into separate branches or sub-branches. For example, if you directly store `TSimpleObject` into `TTree`, each data member will be stored in a separate branch:

```{code-block} Python
import uproot

f = uproot.open("demo_data.root")
f["my_tree/simple_obj"].show()
```
```{code-block} console
---
caption: Output
---
name                                     | typename                 | interpretation                
-----------------------------------------+--------------------------+-------------------------------
simple_obj                               | TSimpleObject            | AsGroup(<TBranchElement 'simpl
TObject                                  | (group of fUniqueID:u... | AsGroup(<TBranchElement 'TO...
TObject/fUniqueID                        | uint32_t                 | AsDtype('>u4')
TObject/fBits                            | uint32_t                 | AsDtype('>u4')
m_int                                    | int32_t                  | AsDtype('>i4')
m_str                                    | std::string              | AsStrings(header_bytes=6)
m_arr_int[5]                             | int32_t[5]               | AsDtype("('>i4', (5,))")
m_vec_double                             | std::vector<double>      | AsJagged(AsDtype('>f8'), he...
m_map_int_double                         | map<int,double>          | AsGroup(<TBranchElement 'm_...
m_map_int_double/m_map_int_double.first  | int32_t[]                | AsJagged(AsDtype('>i4'))
m_map_int_double/m_map_int_double.second | double[]                 | AsJagged(AsDtype('>f8'))
m_map_str_str                            | map<string,TString>      | AsGroup(<TBranchElement 'm_...
m_map_str_str/m_map_str_str.first        | std::string[]            | AsObjects(AsArray(True, Fal...
m_map_str_str/m_map_str_str.second       | TString                  | AsStrings()
m_tstr                                   | TString                  | AsStrings()
m_tarr_int                               | TArrayI                  | AsObjects(Model_TArrayI)
```

This feature makes Uproot easy to read most of the custom classes.

However, if we store `TCStyleArray` defined in [streamer information page](streamer-info.md) into `TTree`, the data members of `TSimpleObject` will not be splitted:

```{code-block} Python
f["my_tree/cstyle_array"].show()
```
```{code-block} console
---
caption: Output
---
name                 | typename                 | interpretation                
---------------------+--------------------------+-------------------------------
m_simple_obj[3]      | TSimpleObject[][3]       | AsObjects(AsArray(False, False
```

This case is more common when you are trying to use uproot-custom.

(obtain-binary-data)=
## Obtain branch binary data

You can obtain the raw binary data of a branch using `uproot.interpretations.custom.AsBinary` interpretation:

```python
from uproot.interpretations.custom import AsBinary

raw_binary = f["my_tree/cstyle_array/m_simple_obj[3]"].array(interpretation=AsBinary())

# Get binary data of entry 0
raw_binary[0].to_numpy()
```
```{code-block} console
---
caption: Output
---
array([ 64,   0,   0, 223,   0,   1,   0,   1,   0,   0,   0,   0,   0,
         0,   0,   0,   0,   0,   0,  32,  64,   0,   0,  15,   0,   9,
        12,  72, 101, 108, 108, 111,  44,  32,  82,  79,  79,  84,  33,
        ...], dtype=uint8)
```

This array is the raw binary data of the first entry of the branch `m_simple_obj[3]`, and it is the data what readers will read.

## Understand the binary data

Binary data is stored as `uint8_t`. In this section, we will explain how to understand the binary data obtained above.

```{note}
The streaming rules are summarized by myself. They may not be complete or accurate. If you find any mistakes, you are welcome to submit an issue or a PR to correct me!
```

(nbytes-version-header)=
### `fNBytes`+`fVersion` header

For many objects, a `fNBytes`+`fVersion` header will be stored ahead of their data members. The `fNBytes` is the left total number of bytes of the object (including `fVersion`), `fVersion` is the version of the object.

`fNBytes` is a 4-byte `uint32_t`. When writing the binary data, `ROOT` sets a bit mask `0x40000000` to the `fNBytes`, so that one can easily check whether the reading is correct. This mask is reflected as a `64` header (i.e. `[64, x, x, x]`) in the `numpy` array. 

For example, the first 4 bytes of the binary data above, `64, 0, 0, 223`, is the `fNBytes` of the first `TSimpleObject`. The `64` usually means the `0x40000000` mask. Unset the mask, we get `0, 0, 0, 223`, which is `223` in `uint32_t`. So the next 223 bytes are the data of this `TSimpleObject`.

The next 2 bytes, `0, 1`, is the `fVersion` of this `TSimpleObject`. `fVersion` is a 2-byte `int16_t`. In this case, the version is `1`.

### The first data member: base class

After the `fNBytes`+`fVersion` header, the binary data starts to correspond to the data members in [the streamer information illustrated before](all-streamer-info-output).

The first data member in the streamer information is `TObject` base class. `ROOT` always put base class first. [This page](https://root.cern/doc/v636/tobject.html) describes each data member of `TObject`. It contains:

1. `fVersion (int16_t)`
2. `fUniqueID (int32_t)`
3. `fBits (uint32_t)`

According to `TObject::Streamer` method in `ROOT` source code, an extra `pidf` will exist if `fBits & (1ULL << 4)` is true (rarely used).

````{admonition} Code implementation
----
class: tip, dropdown
----
The `TObjectReader::read` method implements the reading of `TObject`:

```cpp
void read( BinaryBuffer& buffer ) override {
    buffer.skip_fVersion();
    auto fUniqueID = buffer.read<int32_t>();
    auto fBits     = buffer.read<uint32_t>();

    if ( fBits & ( BinaryBuffer::kIsReferenced ) )
    {
        if ( m_keep_data ) m_pidf->push_back( buffer.read<uint16_t>() );
        else buffer.skip( 2 );
    }

    if ( m_keep_data )
    {
        m_unique_id->push_back( fUniqueID );
        m_bits->push_back( fBits );
        m_pidf_offsets->push_back( m_pidf->size() );
    }
}
```
````

### Subsequent data members

The second data member is `m_int`, which is an `int32_t`. Correspondingly, the next 4 bytes `0, 0, 0, 32` is the value of `m_int`, which is `32`. The third is `m_str`, which is a `std::string` (`fNBytes`+`fVersion`+`fSize`+contents). Similarly, as long as we follow the streamer information, we can understand the binary data step by step.

[](../../reference/binary-format) gives a summary of the binary format of some common classes. It is helpful when you want to implement your own `reader`/`factory`.
