# Investigate your data

Before writing a custom reader or factory, you need to understand two things
about the branch you want to read:

1. **Streamer information** — the metadata that describes the class layout
   (field names, types, nesting).
2. **Binary format** — the raw byte sequence that ROOT writes for each entry.

This page covers both topics in order. By the end you will know exactly what
bytes your reader must consume.

---

## Streamer information

When ROOT writes a custom class to a file, it also writes the class's *streamer
information*: a machine-readable description of every data member and its type.
Understanding this metadata is the first step toward implementing a reader.

### Demo classes

Throughout this page we use two demo classes, `TSimpleObject` and
`TCStyleArray`:

```{code-block} cpp
---
caption: Definition of `TSimpleObject`
---
using namespace std;

class TSimpleObject : public TObject {
  private:
    int m_int{ 32 };

    string m_str{ "Hello, ROOT!" };
    array<int, 5> m_arr_int{ 100, 101, 102, 103, 104 };
    vector<double> m_vec_double{ 1.0, 2.0, 3.0 };

    map<int, double> m_map_int_double{ { 1, 1.0 }, { 2, 2.0 }, { 3, 3.0 } };
    map<string, TString> m_map_str_str{ { "A", "Apple" }, { "B", "Banana" }, { "C", "Cat" } };

    TString m_tstr{ "Hello, ROOT!" };
    TArrayI m_tarr_int{ 5 };

  public:
    TSimpleObject() : TObject() {
        for ( int i = 0; i < m_tarr_int.GetSize(); i++ ) m_tarr_int[i] = i * 10;
    }

    ClassDef( TSimpleObject, 1 );
};
```

```{code-block} cpp
---
caption: Definition of `TCStyleArray`
---
class TCStyleArray : public TObject {
  private:
    TSimpleObject m_simple_obj[3]{ TSimpleObject(), TSimpleObject(), TSimpleObject() };

    ClassDef( TCStyleArray, 1 );
};
```

### Reading streamer information with Uproot

Uproot exposes all streamers stored in a file via `f.file.streamers`:

```python
import uproot

f = uproot.open("file.root")
f.file.streamers
```

```{code-block} console
---
caption: Output (truncated)
---
{'TNamed': {1: <TStreamerInfo for TNamed version 1 at 0x74083a52a840>},
 'TObject': {1: <TStreamerInfo for TObject version 1 at 0x74083a52b140>},
 'TList': {5: <TStreamerInfo for TList version 5 at 0x74083a52bbf0>},
 ...}
```

Look up a specific class by name. The version number is the dictionary key:

```python
f.file.streamers["TSimpleObject"]
```
```{code-block} console
---
caption: Output
---
{1: <TStreamerInfo for TSimpleObject version 1 at 0x74083a5833b0>}
```

```{seealso}
All Uproot streamer classes are documented in
[the Uproot documentation](https://uproot.readthedocs.io/en/latest/uproot.streamers.html).
```

### Human-readable summary

Call `show()` for a compact overview:

```python
streamer = f.file.streamers["TSimpleObject"][1]
streamer.show()
```
```{code-block} console
---
caption: Output
---
TSimpleObject (v1): TObject (v1)
    m_int: int (TStreamerBasicType)
    m_str: string (TStreamerSTLstring)
    m_arr_int: int (TStreamerBasicType)
    m_vec_double: vector<double> (TStreamerSTL)
    m_map_int_double: map<int,double> (TStreamerSTL)
    m_map_str_str: map<string,TString> (TStreamerSTL)
    m_tstr: TString (TStreamerString)
    m_tarr_int: TArrayI (TStreamerObjectAny)
```

### Detailed member attributes

For the full details, use `all_members`:

(simple-obj-streamer-info)=
```python
streamer = f.file.streamers["TSimpleObject"][1]
streamer.all_members
```
```{code-block} console
---
caption: Output
---
{'@fUniqueID': 0,
 '@fBits': 16842752,
 'fName': 'TSimpleObject',
 'fTitle': '',
 'fCheckSum': 2574715488,
 'fClassVersion': 1,
 'fElements': <TObjArray of 9 items at 0x74083a583b90>}
```

Iterate over `elements` to inspect each data member:

```python
[i.all_members for i in streamer.elements]
```
(all-streamer-info-output)=
```{code-block} console
---
caption: Output
---
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
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_str',
  'fTitle': '',
  'fType': 500,
  'fSize': 32,
  'fArrayLength': 0,
  'fArrayDim': 0,
  'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'string',
  'fSTLtype': 365,
  'fCtype': 365},
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_arr_int',
  'fTitle': '',
  'fType': 3,
  'fSize': 20,
  'fArrayLength': 5,
  'fArrayDim': 1,
  'fMaxIndex': array([5, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'int'},
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_vec_double',
  'fTitle': '',
  'fType': 500,
  'fSize': 24,
  'fArrayLength': 0,
  'fArrayDim': 0,
  'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'vector<double>',
  'fSTLtype': 1,
  'fCtype': 8},
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_map_int_double',
  'fTitle': '',
  'fType': 500,
  'fSize': 48,
  'fArrayLength': 0,
  'fArrayDim': 0,
  'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'map<int,double>',
  'fSTLtype': 4,
  'fCtype': 61},
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_map_str_str',
  'fTitle': '',
  'fType': 500,
  'fSize': 48,
  'fArrayLength': 0,
  'fArrayDim': 0,
  'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'map<string,TString>',
  'fSTLtype': 4,
  'fCtype': 61},
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_tstr',
  'fTitle': '',
  'fType': 65,
  'fSize': 24,
  'fArrayLength': 0,
  'fArrayDim': 0,
  'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'TString'},
 {'@fUniqueID': 0,
  '@fBits': 16777216,
  'fName': 'm_tarr_int',
  'fTitle': '',
  'fType': 62,
  'fSize': 24,
  'fArrayLength': 0,
  'fArrayDim': 0,
  'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
  'fTypeName': 'TArrayI'}]
```

Each dictionary maps to one data member of `TSimpleObject`. Key attributes:

| Attribute   | Description |
| ----------- | ----------- |
| `fName`     | Data member name |
| `fType`     | Numeric type code |
| `fTypeName` | Human-readable type name |
| `fArrayDim` | Number of array dimensions (0 = scalar) |
| `fMaxIndex` | Maximum index per dimension |

```{note}
The [ROOT streamer-info reference](https://root.cern/doc/v636/streamerinfo.html)
documents these attributes, though some details may be outdated.
```

### Streamer information in uproot-custom

Uproot-custom rearranges the raw Uproot streamer information into a more
convenient format: a dictionary mapping class names to the list of their data
members' streamer dictionaries. This rearranged dictionary is what gets passed
to `Factory.build_factory`.

```{seealso}
See [](method-build-factory) for the exact signature and format.
```

---

## Binary data

With the streamer information in hand, the next step is to inspect the actual
bytes ROOT writes for each entry. This lets you validate your understanding of
the layout before writing any reader code.

### Object splitting

ROOT usually *splits* top-level data members into separate sub-branches. For
example, storing `TSimpleObject` directly in a `TTree` produces one sub-branch
per member:

```python
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

Uproot handles split branches natively, so this case rarely needs uproot-custom.

However, when the class is stored as a c-style array element — for instance,
`TCStyleArray` defined [above](#demo-classes) — ROOT does **not** split the
members:

```python
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

This is the typical scenario where uproot-custom is needed.

(obtain-binary-data)=
### Obtaining raw binary data

Use `AsBinary` to pull the uninterpreted byte buffer of a branch:

```python
from uproot.interpretations.custom import AsBinary

raw_binary = f["my_tree/cstyle_array/m_simple_obj[3]"].array(interpretation=AsBinary())

# Binary data of entry 0
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

This `uint8` array is exactly what your reader will receive.

### Understanding the byte layout

```{note}
The streaming rules below are summarized empirically. If you find inaccuracies,
please open an issue or pull request.
```

(nbytes-version-header)=
#### `fNBytes` + `fVersion` header

Many ROOT objects begin with a **6-byte header**:

| Field      | Size    | Type       | Notes |
| ---------- | ------- | ---------- | ----- |
| `fNBytes`  | 4 bytes | `uint32_t` | Remaining byte count (including `fVersion`). The high bit `0x40000000` is always set as a validity marker. |
| `fVersion` | 2 bytes | `int16_t`  | Class version |

For the first entry above, the first four bytes `64, 0, 0, 223` form `fNBytes`.
The leading `64` corresponds to the `0x40000000` mask. Stripping the mask gives
`0x000000DF` = **223**, so the next 223 bytes make up this `TSimpleObject`.
The following two bytes `0, 1` are the `fVersion` = **1**.

#### Base class (`TObject`)

After the header, ROOT writes base-class data first. `TObject` contains
([reference](https://root.cern/doc/v636/tobject.html)):

1. `fVersion` (`int16_t`)
2. `fUniqueID` (`int32_t`)
3. `fBits` (`uint32_t`)

If `fBits & (1 << 4)` is set (rare), an extra `uint16_t pidf` follows.

````{admonition} Code example
---
class: tip, dropdown
---
The built-in `TObjectReader::read` method:

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

#### Subsequent data members

After the base class, data members appear in streamer order:

- `m_int` — 4 bytes (`int32_t`). E.g. `0, 0, 0, 32` = **32**.
- `m_str` — `fNBytes` + `fVersion` + length-prefixed content (`std::string`).
- And so on for every member listed in the [streamer output above](#all-streamer-info-output).

Follow the streamer information member by member and you can decode the entire
binary payload.

[](../../reference/binary-format) provides a summary of the binary formats for
common ROOT types — useful reference material when implementing your own reader.

---

```{admonition} Next step
---
class: hint
---
You now know how to inspect streamer information and decode binary bytes.
Move on to [Reader & factory interface](reader-and-factory.md) to learn
the Python APIs and study a full worked example.
```
