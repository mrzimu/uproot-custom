# Get started

`uproot-custom` has already defined several built-in readers and factories. You can firstly try them to see if they can handle your reading task.

## Use built-in factories

### Step 1: Obtain the object-path of branches

To let `uproot-custom` read specific branches, you need to obtain the regularized `object-path` of the branches:

```python
import uproot
import uproot_custom as uc

# Open a ROOT file and get the object-path of a branch
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

### Step 2: Register the branch to `uproot-custom` and read

Record the content of `regularized_obj_path` above. In the next time, you can register the branch to `uproot-custom` **before opening the file**:

```python
import uproot
import uproot_custom as uc

uc.AsCustom.target_branches.add("/my_tree:my_branch")
```

You can print the branch with `show` method:

```python
f["my_tree"].show()
```

As long as the registration is successful, the interpretation of `my_branch` should be `AsCustom`.

````{tip}
`uc.AsCustom.target_branches` is a `set`, you can add multiple branches like this:

```python
uc.AsCustom.target_branches |= {"/my_tree:branch1", "/my_tree:branch2"}
```
````

Now you can read the branch as using `uproot`:

```python
arr = f["my_tree/my_branch"].array() # will be read by uproot-custom
```

### Example

When storing a c-style array `std::vector<double>[3]` into a custom class like:

```{code-block} cpp
---
caption: Class definition
---
class TCStyleArray : public TObject {
public:
  std::vector<double> m_vec_double[3]{ { 1.0, 2.0, 3.0 }, { 4.0, 5.0, 6.0 }, { 7.0, 8.0, 9.0 } };
}
```

```{code-block} cpp
---
caption: Write to `TTree`
---
TTree t("my_tree", "my_tree");

TCStyleArray obj;
t.Branch("cstyle_array", &obj);

for (int i = 0; i < 10; i++) {
  obj = TCStyleArray();
  t.Fill();
}
```

Reading the branch with `uproot-custom`/`uproot` will lead to different results:

```{note}
At the time this document is written, the latest version of `uproot` is `5.6.6`.
```

`````{tab-set}
````{tab-item} uproot-custom
`uproot-custom` can handle this case with the built-in factories:

```python
import uproot
import uproot_custom as uc

# register the branch to uproot-custom
uc.AsCustom.target_branches.add("/my_tree:cstyle_array/m_vec_double[3]")

# open the file and read the branch as usual
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

Use `show` method to inspect the branch:

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

Note that the interpretation is `AsCustom(vector<double>[][3])`, which means `uproot-custom` is used to read this branch.

````
````{tab-item} uproot
Read the branch with `uproot`:

```python
import uproot
f = uproot.open("file.root")
f["my_tree/cstyle_array/m_vec_double[3]"].array()
```

It will throw `DeserializationError`:

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

## Customize `factory` and `reader`

If the built-in factories cannot handle the reading task, you need to implement your own `factory` and/or `reader`. This requires some knowledge of `ROOT`'s streaming mechanism and `uproot-custom`'s design.

You can start from reading examples for a quick overview. For a deeper understanding of the design, read the architecture documents.
