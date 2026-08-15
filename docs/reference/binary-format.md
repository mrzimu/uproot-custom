# Binary format of common classes

```{attention}
This page is a growing checklist. Use it alongside the walkthrough in
[](../tutorial/customize-factory-reader/investigate-data.md) when inspecting bytes.
```

This section describes the binary format of common ROOT classes, organized by the
class categories that `uproot-custom` handles. Each category corresponds to a
pipeline component that matches a C++ type from streamer
information and navigates the binary bytes.

Data are stored in **big-endian** format.

```{note}
These formats are summarized by me, and may not be complete or accurate. If you
find any mistakes, you are welcome to open an issue or a PR to correct them.
```

## Class correspondence

| Class | Matches |
|---|---|
| Primitive types | `bool`, `char`, `short`, `int`, `long`, `float`, `double`, `uint*`, `int*_t`, `uint*_t`, `Bool_t`, `Char_t`, … |
| `std::string` | `std::string` |
| `TString` | `TString` |
| `TArray` | `TArrayC`, `TArrayS`, `TArrayI`, `TArrayL`, `TArrayL64`, `TArrayF`, `TArrayD` |
| `std::vector` (and other STL sequences) | `std::vector`, `std::list`, `std::set`, `std::multiset`, `std::unordered_set`, `std::unordered_multiset` |
| `std::map` (and other STL maps) | `std::map`, `std::unordered_map`, `std::multimap`, `std::unordered_multimap` |
| `TObject` | `TObject` as base class (fType=66) |
| C-style array / `std::array` | C-style arrays (`T m_data[N]`) and `std::array` (`fArrayDim > 0` or jagged) |
| Any class | Arbitrary class objects (fType=0 or no special fType) |
| Base class | Base class embedding (fType=0 with `BASE` typename) |
| Pointer (`T*`) | Pointer-to-object (`fType` in {63, 64, 68, 69} or `fTypeName` ends with `*`) |
| Group | Explicit grouping of sub-readers (never auto-matched) |
| Empty | Placeholder (never auto-matched) |

## Common header patterns

Several binary patterns appear repeatedly across different types. They are
summarized here for reference.

### `fNBytes` (4 bytes, uint32)

A 4-byte big-endian unsigned integer whose high bit (`kByteCountMask = 0x40000000`)
is **always set**. The actual byte count is `fNBytes & ~kByteCountMask`.

```console
# Example: fNBytes = 12
64, 0, 0, 12 → byte_count = 12 (64 is the high bit set)
```

### `fVersion` (2 bytes, int16)

A 2-byte big-endian signed integer indicating the class version. When `fVersion == 0`,
a 4-byte checksum follows immediately.

```console
# Example: fVersion = 3
0, 3

# Example: fVersion = 0 (with checksum)
0, 0, 255, 255, 255, 255 → fVersion=0, checksum=0xFFFFFFFF
```

### `fNBytes + fVersion` header (object header)

Almost every non-trivial class object is prefixed with:

```
[fNBytes: uint32] [fVersion: int16] [checksum?: uint32 if fVersion==0]
```

### `kStreamedMemberwise` flag (bit 14 of `fVersion`)

When `fVersion & (1 << 14) != 0` (i.e. the first byte is `64`), the object is stored in **member-wise** order — all
values of the first member, then all values of the second member, etc. The default
is **object-wise** order — each object's members are stored contiguously.

---

## Primitive types

**Matches:** `bool`, `char`, `short`, `int`, `long`, `long long`, `float`, `double`,
and their `signed`/`unsigned` variants, `int*_t`/`uint*_t`, ROOT typedefs (`Bool_t`,
`Int_t`, …).

**Identification:** `fType` in {1,2,3,4,5,8,11,12,13,14,16,17,18} or `fTypeName`
matches a known primitive type name.

Primitive types are stored as **raw big-endian bytes** with no length prefix or header.

```{list-table} Primitive type sizes
:header-rows: 1

* - Type
  - Size (bytes)
  - struct format
* - `bool`
  - 1
  - `>B`
* - `char` / `int8_t` / `uint8_t`
  - 1
  - `>b` / `>B`
* - `short` / `int16_t` / `uint16_t`
  - 2
  - `>h` / `>H`
* - `int` / `int32_t` / `uint32_t`
  - 4
  - `>i` / `>I`
* - `long` / `int64_t` / `uint64_t`
  - 8
  - `>q` / `>Q`
* - `float`
  - 4
  - `>f`
* - `double`
  - 8
  - `>d`
```

`````{tab-set}

````{tab-item} single element
```{code-block} cpp
---
caption: Data member definition
---
int m_int = 42;
uint16_t m_uint16 = 65535;
double m_double = 3.14159;
```

```{code-block} console
---
caption: Binary format
---
# m_int
0, 0, 0, 42

# m_uint16
255, 255

# m_double
64, 9, 33, 249, 240, 27, 134, 110
```
````

````{tab-item} C-style array and std::array
```{code-block} cpp
---
caption: Data member definition
---
int m_int[3] = { 1, 2, 3 };
std::array<uint16_t, 3> m_uint16 = { 65535, 0, 42 };
double m_double[2][2] = { { 1.0, 2.0 }, { 3.0, 4.0 } };
```

```{code-block} console
---
caption: Binary format
---
# m_int[3]
0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3

# std::array<uint16_t, 3>
255, 255, 0, 0, 0, 42

# m_double[2][2]
64, 16, 0, 0, 0, 0, 0, 0, 64, 8, 0, 0, 0, 0, 0, 0, 64, 0, 0, 0, 0, 0, 0, 0, 63, 240, 0, 0, 0, 0, 0, 0
```
````
`````

---

## `std::string`

**Matches:** `std::string` (`fTypeName` starts with `string`).

```
[length: uint8] [data: bytes...]
```

If the first byte is `255`, the length is instead a 4-byte `uint32`:

```
[255: uint8] [length: uint32] [data: bytes...]
```

When wrapped in a C-style or `std::array`, a `fNBytes + fVersion` header may
precede the string data — see [C-style array / `std::array`](#c-style-array-stdarray).

```{code-block} cpp
---
caption: Data member definition
---
std::string m_str = "Hello";
```

```{code-block} console
---
caption: Binary format
---
# m_str ("Hello" = 5 bytes)
5, 72, 101, 108, 108, 111
|  H    e    l    l    o
```

---

## TString

**Matches:** `TString` (ROOT's string class).

Unlike `std::string`, `TString` does **not** have a `fNBytes + fVersion` header
by default. However, when stored inside a C-style or `std::array`, the header is
present.

```
[length: uint8] [data: bytes...]
```

If the first byte is `255`, the length is instead a 4-byte `uint32`:

```
[255: uint8] [length: uint32] [data: bytes...]
```

```{code-block} cpp
---
caption: Data member definition
---
TString m_tstr = "ROOT";
```

```{code-block} console
---
caption: Binary format
---
# m_tstr ("ROOT" = 4 bytes)
4, 82, 79, 79, 84
|  R   O   O   T
```

---

## TArray

**Matches:** `TArrayC`, `TArrayS`, `TArrayI`, `TArrayL`, `TArrayL64`, `TArrayF`,
`TArrayD`.

```
[length: uint32] [data: element*length]
```

```{list-table} TArray type mapping
:header-rows: 1

* - Class
  - Element dtype
  - Element size
* - `TArrayC`
  - `int8`
  - 1
* - `TArrayS`
  - `int16`
  - 2
* - `TArrayI`
  - `int32`
  - 4
* - `TArrayL`
  - `int64`
  - 8
* - `TArrayL64`
  - `int64`
  - 8
* - `TArrayF`
  - `float32`
  - 4
* - `TArrayD`
  - `float64`
  - 8
```

```{code-block} cpp
---
caption: Data member definition
---
TArrayI m_arr = { 10, 20, 30 };
```

```{code-block} console
---
caption: Binary format
---
# m_arr (3 elements)
0, 0, 0, 3, 0, 0, 0, 10, 0, 0, 0, 20, 0, 0, 0, 30
|  length |  element 1   |  element 2   |  element 3
```

---

## `std::vector` (and other STL sequences)

**Matches:** `std::vector`, `std::list`, `std::set`, `std::multiset`,
`std::unordered_set`, `std::unordered_multiset`.

**Identification:** `fTypeName` starts with one of the `target_types` names.

### Single element

```
[fNBytes: uint32] [fVersion: int16] [checksum?: uint32]
[length: uint32] [element 1] [element 2] ... [element N]
```

### C-style array of STL containers

When storing as a C-style array (e.g. `std::vector<int> m_vec[2]`), the outer
`fNBytes + fVersion` header is kept, and each element is stored as a separate
sequence with its own length prefix.

### std::array of STL containers

When storing as `std::array` (e.g. `std::array<std::vector<int>, 2>`), there is
**no** outer `fNBytes + fVersion` header. Each element is stored as a sequence
with its own length prefix.

`````{tab-set}

````{tab-item} single element
```{code-block} cpp
---
caption: Data member definition
---
std::vector<int> m_vec_int = { 1, 2, 3 };
std::list<uint16_t> m_list_uint16 = { 65535, 0, 42 };
```

```{code-block} console
---
caption: Binary format
---
# m_vec_int
64, x, x, x, 0, x, 0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3
fNBytes+fVersion |  length   |            3 elements            |

# m_list_uint16
64, x, x, x, 0, x, 0, 0, 0, 3, 255, 255, 0, 0, 0, 42
fNBytes+fVersion |  length   | 3 elements (uint16) |
```
````

````{tab-item} C-style array
```{code-block} cpp
---
caption: Data member definition
---
std::vector<uint16_t> m_vec_uint16[2] = { { 1, 2, 3 }, { 4, 5 } };
```

```{code-block} console
---
caption: Binary format
---
# m_vec_uint16[2]
64, x, x, x, 0, x, 0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 2, 0, 0, 0, 4, 0, 0, 0, 5
fNBytes+fVersion |  length   |            3 elements             |  length   |      2 elements      |
```
````

````{tab-item} std::array
```{code-block} cpp
---
caption: Data member definition
---
std::array<std::vector<uint16_t>, 2> m_arr_vec_uint16 = { { { 1, 2, 3 }, { 4, 5 } } };
```

```{code-block} console
---
caption: Binary format
---
# m_arr_vec_uint16 (no outer header)
0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 2, 0, 0, 0, 4, 0, 0, 0, 5
|  length |            3 elements             |  length   |      2 elements      |
```
````
`````

### Member-wise vs object-wise

The `fVersion` field may have the `kStreamedMemberwise` bit (bit 14) set. When
set, the elements are stored member-wise: all first members of each element,
then all second members, etc. This is handled by the `read_many_memberwise` methods
in the reader hierarchy.

---

## `std::map` (and other STL maps)

**Matches:** `std::map`, `std::unordered_map`, `std::multimap`,
`std::unordered_multimap`.

**Identification:** `fTypeName` starts with one of the `target_types` names.

```
[fNBytes: uint32] [fVersion: int16] [checksum?: uint32]
[length: uint32] [key 1] [val 1] [key 2] [val 2] ... [key N] [val N]
```

```{code-block} cpp
---
caption: Data member definition
---
std::map<int, float> m_map = { {1, 1.5f}, {2, 2.5f}, {3, 3.5f} };
```

```{code-block} console
---
caption: Binary format (object-wise)
---
# m_map
64, x, x, x, 0, x, 0, 0, 0, 3, 0, 0, 0, 1, 63, 192, 0, 0, 0, 0, 0, 2, 64, 32, 0, 0, 0, 0, 0, 3, 64, 96, 0, 0
fNBytes+fVersion |  length |  key 1 |   val 1   |  key 2 |   val 2   |  key 3 |   val 3
```

When `kStreamedMemberwise` is set, keys and values are stored separately:

```
[fNBytes: uint32] [fVersion: int16] [elem_version: int16] [elem_checksum?: uint32]
[length: uint32] [key 1] [key 2] ... [key N] [val 1] [val 2] ... [val N]
```

---

## TObject

**Matches:** `TObject` as a base class (`fType=66`).

```
[fVersion: int16] [fUniqueID: uint32] [fBits: uint32] [pidf?: uint16]
```

```{code-block} console
---
caption: Binary format
---
# TObject
0, 3, 0, 0, 0, 42, 0, 0, 0, 0
fVer | fUniqueID  |   fBits
```

By default the data is discarded (`keep_data=False`), producing an
`EmptyArray` in the output.

---

## C-style array / `std::array`

**Matches:** Data members with `fArrayDim > 0` (C-style arrays or `std::array`),
or jagged branches (variable-length arrays).

**Identification:** `fArrayDim > 0` in the streamer info, or `is_jagged=True`
from `get_dims_from_branch`. The dimensions are stored in `fMaxIndex[0..fArrayDim-1]`.

**Priority:** 20 (evaluated before other categories, so it wraps the element
correctly).

### How C-style array / `std::array` modifies contained types

The element is wrapped by an *element handler* for the contained type. When the array
is `std::array` (identified by `fType=82`), the element is called with
`in_std_array=True`, which suppresses the `fNBytes + fVersion` header for
`std::vector` (and other STL sequences), `std::map` (and other STL maps), and `std::string`.

When `TString` is inside a C-style or `std::array`, its `with_header` flag is
set to `True` (unlike standalone `TString`).

### Fixed-size

Elements are concatenated with no separators or length prefixes:

```
[element 1] [element 2] ... [element N]
```

### Jagged / variable-length

```
[element 1] [element 2] ... [element N]
```

The entry boundaries are determined by the entry offsets array, not by a
fixed count. The reader reads elements until it reaches the next entry's
start offset.

### Awkward reconstruction

For fixed-size arrays, the flat elements are wrapped in `RegularArray` layers
corresponding to the dimensions in `fMaxIndex`. For jagged arrays, a
`ListOffsetArray` wraps the elements.

---

## Any class

**Matches:** Any class object that is not handled by a more specific category.
This is the **fallback** (priority=0).

**Identification:** `fTypeName` is a class name found in `all_streamer_info`,
and `fTypeName` does not end with `*` (pointer types go to Pointer (`T*`)).

```
[fNBytes: uint32] [fVersion: int16] [checksum?: uint32 if fVersion==0]
[member 1 data] [member 2 data] ... [member N data]
```

The total size of member data must equal `fNBytes` — the reader verifies this
with an assertion.

```{code-block} cpp
---
caption: Example class definition
---
class MyClass {
    int   m_a;
    float m_b;
};
```

```{code-block} console
---
caption: Binary format for MyClass{m_a=42, m_b=3.14f}
---
# fNBytes=8, fVersion=1
0, 0, 0, 8, 0, 1, 0, 0, 0, 42, 64, 72, 245, 195
fNBytes   |fVer|  m_a=42    |  m_b=3.14f
```

### Member-wise reading

When reading in member-wise mode, all values of member 1 are read first,
then all values of member 2, etc. — rather than reading each object as a whole.

---

## Base class

**Matches:** Base class embedding, identified by `fType=0` and `fTypeName="BASE"`.

The binary format is the same as the base class's members concatenated —
**no additional `fNBytes + fVersion` header** is added by the base class itself.

```
[base member 1 data] [base member 2 data] ... [base member N data]
```

---

## Pointer (`T*`)

**Matches:** Pointer-to-object members: `fType` in {63 (`kObjectp`), 64
(`kObjectP`), 68 (`kAnyp`), 69 (`kAnyP`)} or `fTypeName` ends with `*`.

**Priority:** 15 (evaluated after C-style array / `std::array` but before most others).

### read_object_any

```
[bcnt: uint32] [tag: uint32?] [classname?: null-terminated string] [object data?]
```

Two cases for the first bytes:

1. **Versioned** (`bcnt & kByteCountMask != 0` and `bcnt != kNewClassTag`):
   `fNBytes = bcnt & ~kByteCountMask`, then `tag = read_uint32()`.

2. **Unversioned** (`bcnt & kByteCountMask == 0` or `bcnt == kNewClassTag`):
   `tag = bcnt`, `fNBytes = 0`.

Then the tag is interpreted:

| tag value | Meaning | Action |
|---|---|---|
| `0` | Null pointer | Store `-1` as index |
| `1` | `kAnyP` (unsupported) | Raise `NotImplementedError` |
| `tag & kClassMask == 0` (nonzero) | Reference to a previously-read object | Look up `stream.refs[tag]`, store the object index |
| `kNewClassTag` (0xFFFFFFFF) | New class, new object | Read null-terminated classname, register class ref, read object data, register object ref, increment counter |
| `tag & kClassMask != 0` | Known class, new object | Read object data, register object ref, increment counter |

The reference table (`stream.refs`) maps `ref_begin + kMapOffset` (versioned) or
`len(stream.refs) + 1` (unversioned) to a `_Reference`.

```{code-block} cpp
---
caption: Data member definition
---
MyClass* m_ptr = new MyClass(42, 3.14f);  // non-null pointer
MyClass* m_null = nullptr;                  // null pointer
```

```{code-block} console
---
caption: Binary format (versioned, new class)
---
# m_ptr: bcnt=0x40000014, tag=kNewClassTag
64, 0, 0, 20, 255, 255, 255, 255, 77, 121, 67, 108, 97, 115, 115, 0, 0, 0, 0, 8, 0, 1, 0, 0, 0, 42, 64, 72, 245, 195
fNBytes=20  |  kNewClassTag   | "MyClass\0"                    |   MyClass object data

# m_null: bcnt=0, tag=0
0, 0, 0, 0
tag=0 (null)
```

### Awkward reconstruction

Pointer (`T*`) produces an `IndexedOptionArray`:
- `element_idxs[i] == -1` → null pointer (None)
- `element_idxs[i] >= 0` → index into the element content array

---

## Appendix: Streamer info fields reference

Key fields in the streamer information dictionary:

| Field | Type | Description |
|---|---|---|
| `fName` | string | Data member name |
| `fType` | int | Type code (see below) |
| `fTypeName` | string | C++ type name (e.g. `int`, `vector<float>`, `MyClass`) |
| `fSize` | int | Size in bytes (for primitive types) |
| `fArrayDim` | int | Number of array dimensions (0 = scalar) |
| `fMaxIndex` | int[5] | Size of each dimension |
| `fArrayLength` | int | Total number of elements |

### Common `fType` values

| fType | Meaning |
|---|---|
| 0 | `BASE` (base class) or class object |
| 1 | `char` |
| 2 | `short` |
| 3 | `int` |
| 4 | `long` |
| 5 | `float` |
| 8 | `double` |
| 11 | `unsigned char` |
| 12 | `unsigned short` |
| 13 | `unsigned int` |
| 14 | `unsigned long` |
| 16 | `long long` |
| 17 | `unsigned long long` |
| 18 | `bool` |
| 63 | `kObjectp` (pointer to TObject) |
| 64 | `kObjectP` (pointer to TObject) |
| 66 | `TObject` base class |
| 68 | `kAnyp` (pointer to any object) |
| 69 | `kAnyP` (pointer to any object) |
| 82 | `std::array` |
