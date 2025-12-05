# Streamer information

When storing custom classes in `ROOT`, `ROOT` stores the class's streamer information in the file. The streamer information contains the class's data members and their types. When reading the class from file, `ROOT` reads the streamer information first, then reads the binary data according to the streamer information.

Before continuing, we define a demo custom class `TSimpleObject` and `TCstyleArray` in C++. `TSimpleObject` contains various data members of different types, `TCStyleArray` contains an c-style array of `TSimpleObject`:

```{code-block} cpp
---
caption: Definition of `TSimpleObject`
---
using namespace std;

class TSimpleObject : public TObject {
  private:
    // --------- Simple types ---------
    int m_int{ 32 };

    // --------- Simple STL ---------
    string m_str{ "Hello, ROOT!" };

    // std::array
    array<int, 5> m_arr_int{ 100, 101, 102, 103, 104 };

    // Sequence like containers
    vector<double> m_vec_double{ 1.0, 2.0, 3.0 };

    // Mapping like containers
    map<int, double> m_map_int_double{ { 1, 1.0 }, { 2, 2.0 }, { 3, 3.0 } };
    map<string, TString> m_map_str_str{ { "A", "Apple" }, { "B", "Banana" }, { "C", "Cat" } };

    // --------- ROOT objects ---------
    TString m_tstr{ "Hello, ROOT!" };
    TArrayI m_tarr_int{ 5 };

  public:
    TSimpleObject() : TObject() {
        // Fill TArrayI
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

In the following sections, we will use `TSimpleObject` and `TCStyleArray` as an example to illustrate how `ROOT` stores custom classes.

## Streamer information in Uproot

Uproot can read the streamer information stored in the file. To obtain all streamer information, you can use:

```python
import uproot

f = uproot.open("file.root")
f.file.streamers
```

You can see plenty of streamers in the output:

```{code-block} console
---
caption: Output
---
{'TNamed': {1: <TStreamerInfo for TNamed version 1 at 0x74083a52a840>},
 'TObject': {1: <TStreamerInfo for TObject version 1 at 0x74083a52b140>},
 'TList': {5: <TStreamerInfo for TList version 5 at 0x74083a52bbf0>},
 'TSeqCollection': {0: <TStreamerInfo for TSeqCollection version 0 at 0x74083a538380>},
 ...}
```

As long as the `TSimpleObject` is stored in the file, you can find its streamer information:

```python
f.file.streamers["TSimpleObject"]
```
```{code-block} console
---
caption: Output
---
{1: <TStreamerInfo for TSimpleObject version 1 at 0x74083a5833b0>}
```

The key `1` is the version number of `TSimpleObject`, the value is corresponding `TStreamerInfo` object.

```{seealso}
You can find all Uproot streamer information classes in [the documentation](https://uproot.readthedocs.io/en/latest/uproot.streamers.html).
```

Using `show` method you can print the streamer information:

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

Using `all_members` attribute, you can see full details of the streamer information:

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

Print `all_members` of `TSimpleObject`'s data members:

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

This list of `all_members` corresponds to the data members defined in `TSimpleObject`. Each data member is represented by a dictionary containing its attributes, such as `fName`, `fType`, `fSize`, `fArrayLength`, and `fTypeName`.

A brief description of some important attributes is given in the table below:

| Attribute   | Description |
| ----------- | ----------- |
| `fName`     | Name of the data member |
| `fType`     | Type code of the data member |
| `fTypeName` | Type name of the data member |
| `fArrayDim` | Number of dimensions if the data member is an array |
| `fMaxIndex` | Maximum index of the `fArrayDim` if the data member is an array |

```{note}
[ROOT streamer info page](https://root.cern/doc/v636/streamerinfo.html) provides some explanations of the attributes in `all_members`. But the page seems not updated for a long time, some details are missing.
```

## Streamer information in uproot-custom

The streamer information in uproot-custom will be passed to `factory` to handle data members. To simplify the usage of streamer information, uproot-custom rearranges the streamer information into a more convenient format: A dictionary of class names to the list of their data members' streamer information.

```{seealso}
You can find the concrete format of the rearranged streamer information in [factory interface page](method-build-factory).
```
