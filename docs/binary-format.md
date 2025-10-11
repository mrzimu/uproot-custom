# Binary format of common classes

```{attention}
This page is still under construction.
```

This section lists the binary format of some common classes. Data are stored in big-endian format.

```{note}
These formats are summarized by me, and may not be complete or accurate. If you find any mistakes, you are welcome to open an issue or a PR to correct them.
```

## C-style arrays and `std::array`

C-style arrays are those data members defined as `T m_data[N]`. When data members are stored as C-style arrays or `std::array`, the streaming rules may be different. In the following sections, both cases are listed. 

For both C-style arrays and `std::array`, you can identify them by checking the `fArrayDim` field in the streamer information. `fArrayDim` indicates the number of dimensions of the array. The concrete dimensions are stored in the `fMaxIndex` field as an array of 5 integers.

For example, for a data member defined as `T m_data[3][4]`, the streamer information will have `fArrayDim` equal to 2, and `fMaxIndex` equal to `[3, 4, 0, 0, 0]`.

## Primitive types

A common streamer information of primitive types is as follows:

```python
{'@fUniqueID': 0,
 '@fBits': 16777216,
 'fName': 'm_int',
 'fTitle': '',
 'fType': 3,
 'fSize': 4,
 'fArrayLength': 0,
 'fArrayDim': 0,
 'fMaxIndex': array([0, 0, 0, 0, 0], dtype='>i4'),
 'fTypeName': 'int'}
```

For primitive types, data are directly written in binary format:

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

<!-- TODO: Test nested std::array -->

## Sequence-like STL containers

"Sequence-like" STL containers include `std::vector`, `std::list`, `std::set`, etc. They all store one kind of data. In `ROOT`, they are all stored as a sequence of elements, with a `fNBytes`+`fVersioni` header, a 4-byte length prefix, then the elements.

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

When storing as C-style array, the `fNBytes`+`fVersion` header is kept, and each element is stored as a sequence with its own length prefix.

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
# m_vec_int[2]
64, x, x, x, 0, x, 0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 2, 0, 0, 0, 4, 0, 0, 0, 5
fNBytes+fVersion |  length   |            3 elements             |  length   |      2 elements      |
```
````

````{tab-item} std::array

When storing as `std::array`, there is no `fNBytes`+`fVersion` header, each element is stored as a sequence with its own length prefix.

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
# m_arr_vec_uint16
0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 2, 0, 0, 0, 4, 0, 0, 0, 5
|  length |            3 elements             |  length   |      2 elements      |
```
````
`````

