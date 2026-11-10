# Get started

Uproot-custom ships with built-in readers and factories that handle most common data types out of the box. This page walks you through the key steps — **finding a branch**, **registering it**, **choosing a technical route**, and **reading it** — so you can start working with your data right away.

## Before you start

```bash
pip install uproot-custom
```

That is the whole installation: `uproot`, `awkward`, `numpy` and `detree-vm` come with it, and no compiler is needed unless you also take the [C++ stage](advanced/cpp-reader.md) of the Python + C++ route. The package is imported as `uproot_custom`, and it requires Python 3.9 – 3.14 (see [version requirements](reference/version-requirements.md)).

## Step 1: Obtain the object-path of a branch

Uproot-custom identifies branches by their *object-path*, with the trailing `;N` cycle number dropped. Take the path off the branch you want to read; `regularize_object_path` shows the form that is stored, and `claim` applies it for you:

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

An object-path joins the tree and the branch with `:`, separates the levels below with `/`, and carries the cycle number as a trailing `;N`, so a literal `branch.object_path` reads `/my_tree;1:my_branch`. `regularize_object_path` drops the cycle number, which is the form the claim set holds; `claim` regularizes for you, so either form can be passed to it.

```{note}
Register the branch that carries the bytes. When ROOT splits a class, the parent branch is a group with no data of its own; registering it and reading it fails inside Uproot with a message about baskets (`entries in normal baskets (0) ... don't add up`), before Uproot-custom is involved. The branch to register is the one whose interpretation names your class, for example `/my_tree:entry/m_obj`.
```

## Step 2: Register the branch

Register the regularized path **before the branch's interpretation is first computed**. Uproot computes an interpretation lazily for each branch object and caches it on that object, so the registration must be in place before anything inspects or reads the branch — `branch.interpretation`, `branch.array()`, `arrays()`, and `tree.show()`, which touches every branch below it. Opening the file computes nothing, so the workflow above is fine: open, inspect the paths, register, then read.

```python
import uproot
import uproot_custom as uc

uc.claim("/my_tree:my_branch")

f = uproot.open("file.root")
f["my_tree"].show()
```

Once the registration succeeds, `f["my_tree"].show()` lists the branch with the `AsCustom` interpretation.

Because that `show()` call computes an interpretation for every branch of the tree, a path registered afterwards has no effect on this file object. Register every branch first, or start over:

```python
f = uproot.open("file.root")          # a fresh file object matches again
```

Within one file object, the same branch object is returned on every lookup, so the cached choice can also be dropped explicitly — `branch._interpretation = None` — but that attribute is private to Uproot and may change.

````{tip}
`uc.claim` takes one object-path or an iterable of them, so several branches register in one call:

```python
uc.claim(["/my_tree:branch1", "/my_tree:branch2"])
```
````

```{tip}
Keep the set of claimed branches minimal — only claim the branches that Uproot-custom should handle.
```

## Step 3: Choose a technical route

There are two routes for decoding a branch, and the **reader backend** selects which one runs. The code default is `cpp`; the recommended setting for a downstream project is `detree`.

| Route | Backend | Use it when |
| ----- | ------- | ----------- |
| **Detree** (recommended) | `detree` | you write the reader once, in Python source, with no build step |
| **Python + C++** | `python` while developing, `cpp` in production | the read path needs plain Python, or Detree is not fast enough |

```python
import uproot_custom as uc

uc.set_backend("detree")   # the recommended backend
```

You can also select it once for the whole session with the `UPROOT_CUSTOM_READER_BACKEND` environment variable, or temporarily with `with uc.use_backend("detree"):`. The backend is consulted again for every basket, and the reader is rebuilt from the factory each time, so a `set_backend` or a `use_backend` block takes effect from the next read onwards. Setting it once at the top of a script is a convention that makes the intent visible, not a hard requirement; only the environment variable is read once and then remembered.

```{warning}
There is no silent fallback. If a class's factory does not implement the selected backend's reader, the first read raises `NotImplementedError`; a read never switches backends on its own. The built-in factories implement the Detree reader as well as the Python and C++ ones.
```

See [choosing a technical route](concepts/choosing-a-route.md) for the trade-offs, and [writing your own reader](tutorial/index.md) when the built-in factories cannot decode a class.

## Step 4: Read the data

```python
arr = f["my_tree/my_branch"].array()
```

```{tip}
The backend is a runtime choice, so the same script can compare backends: read a branch inside `with uc.use_backend("python"):` and compare the array with the Detree result.
```

## Example: Uproot-custom vs Uproot

The following example demonstrates a case that Uproot cannot handle on its own: a c-style array of `std::vector<double>` stored inside a custom class.

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
````{tab-item} Uproot-custom
```python
import uproot
import uproot_custom as uc

uc.claim("/my_tree:cstyle_array/m_vec_double[3]")

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

Inspect the branch to confirm Uproot-custom is active:

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

The interpretation `AsCustom(vector<double>[][3])` confirms Uproot-custom is being used.
````
````{tab-item} Uproot (without Uproot-custom)
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

## Next steps

- [How it works](concepts/how-it-works.md) — the factory / reader / backend pipeline behind these steps.
- [Choosing a technical route](concepts/choosing-a-route.md) — what Detree and the Python + C++ route each cost.
- [Write your own reader](tutorial/index.md) — add a Detree reader for a class the built-in factories cannot decode.
