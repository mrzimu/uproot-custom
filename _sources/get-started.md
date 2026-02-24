# Get started

Uproot-custom ships with built-in readers and factories that handle most
common data types out of the box. This page walks you through the two key
steps — **registering a branch** and **reading it** — so you can start
working with your data right away.

## Step 1: Obtain the object-path of a branch

Uproot-custom identifies branches by their *regularized object-path*.
To find the path for a branch, open the file with Uproot and call
`regularize_object_path`:

```python
import uproot
import uproot_custom as uc

f = uproot.open("file.root")
obj_path = f["my_tree/my_branch"].object_path

regularized_obj_path = uc.regularize_object_path(obj_path)
print(regularized_obj_path)
```
```{code-block} console
---
caption: Output
---
/my_tree:my_branch
```

## Step 2: Register the branch and read

Register the regularized path **before** opening the file. Uproot caches
interpretations on first access, so late registration will have no effect.

```python
import uproot
import uproot_custom as uc

uc.AsCustom.target_branches.add("/my_tree:my_branch")

f = uproot.open("file.root")
f["my_tree"].show()
```

Once the registration succeeds, the branch's interpretation should display as
`AsCustom`:

````{tip}
`uc.AsCustom.target_branches` is a `set`. You can register several branches at
once:

```python
uc.AsCustom.target_branches |= {"/my_tree:branch1", "/my_tree:branch2"}
```
````

Now read the data as you normally would with Uproot:

```python
arr = f["my_tree/my_branch"].array()  # read by uproot-custom
```

```{tip}
Keep the set of target branches minimal — only register the branches that
uproot-custom should handle.
```

## Example: uproot-custom vs Uproot

The following example demonstrates a case that Uproot cannot handle on its own:
a c-style array of `std::vector<double>` stored inside a custom class.

```{code-block} cpp
---
caption: Class definition
---
class TCStyleArray : public TObject {
public:
  std::vector<double> m_vec_double[3]{
    { 1.0, 2.0, 3.0 },
    { 4.0, 5.0, 6.0 },
    { 7.0, 8.0, 9.0 }
  };
}
```

```{code-block} cpp
---
caption: Write to TTree
---
TTree t("my_tree", "my_tree");

TCStyleArray obj;
t.Branch("cstyle_array", &obj);

for (int i = 0; i < 10; i++) {
  obj = TCStyleArray();
  t.Fill();
}
```

`````{tab-set}
````{tab-item} uproot-custom
```python
import uproot
import uproot_custom as uc

uc.AsCustom.target_branches.add("/my_tree:cstyle_array/m_vec_double[3]")

f = uproot.open("file.root")
f["my_tree/cstyle_array/m_vec_double[3]"].array()
```
```{code-block} console
---
caption: Output
---
[[[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
 [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]]]
-------------------------------------
backend: cpu
nbytes: 1.1 kB
type: 10 * var * 3 * var * float64
```

Inspect the branch to confirm uproot-custom is active:

```python
f["my_tree/cstyle_array/m_vec_double[3]"].show()
```
```{code-block} console
---
caption: Output
---
name                 | typename                 | interpretation
---------------------+--------------------------+-------------------------------
m_vec_double[3]      | vector<double>[][3]      | AsCustom(vector<double>[][3])
```

The interpretation `AsCustom(vector<double>[][3])` confirms uproot-custom is
being used.
````
````{tab-item} Uproot (without uproot-custom)
```python
import uproot
f = uproot.open("file.root")
f["my_tree/cstyle_array/m_vec_double[3]"].array()
```

This raises a `DeserializationError`:

```{code-block} console
---
caption: Output
---
DeserializationError: expected 90 bytes but cursor moved by 34 bytes (through std::vector<double>)
in file file.root
in object /my_tree;1
```
````
`````
