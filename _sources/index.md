# Introduction

Uproot-custom is an extension of [Uproot](https://uproot.readthedocs.io/en/latest/basic.html) that provides an enhanced way to read custom classes stored in `TTree`.

## What uproot-custom can do

Uproot-custom can natively read complicated combinations of nested classes and c-style arrays (e.g. `map<int, map<int, map<int, string>>>`, `vector<TString>[3]`, etc), and memberwisely stored classes. It also exposes a way for users to implement their own readers for custom classes that are not supported by Uproot or uproot-custom built-in readers.

## When to use uproot-custom

Uproot-custom aims to handle cases that classes are too complex for Uproot to read, such as when their `Streamer` methods are overridden or some specific data members are not supported by Uproot.

## How uproot-custom works

Uproot-custom uses a `reader`/`factory` mechanism to read classes:

```{mermaid}
flowchart TD
    subgraph py["Python field"]
        direction TB
        AsCustom --> fac["Factory (Primitive, STLVector, TString, ...)"]
        fac["Factory (Primitive, STLVector, TString, ...)"] -- Optional --> form(["construct awkward forms"])
        fac --> build_reader(["build corresponding C++ reader"])
        fac --> build_ak(["construct awkward arrays"])
    end

    user_fac["User's Factory"] -. Register .-> fac

    subgraph cpp["C++ field"]
        direction TB
        build_reader --> reader["C++ Reader"]
        reader --> read_bin(["read binary data"])
        read_bin --> ret_data(["return data"])
    end

    ret_data --> raw_data[("tuple, list, numpy arrays, ...")]
    raw_data --> build_ak
```

- `reader` is a C++ class that implements the logic to read data from binary buffers.
- `factory` is a Python class that creates, combines `reader`s, and post-processes the data read by `reader`s.

This machanism is implemented as `uproot_custom.AsCustom` interpretation. This makes uproot-custom well compatible with Uproot.

```{tip}
Users can implement their own `factory` and `reader`, register them to uproot-custom. An example of implementing a custom `factory`/`reader` can be found in [the example repository](https://github.com/mrzimu/uproot-custom-example).
```

```{note}
Uproot-custom does not provide a full reimplementation of `ROOT`'s I/O system. Users are expected to implement their own `factory`/`reader` for their custom classes that built-in factories cannot handle.
```

```{toctree}
---
maxdepth: 2
hidden: true
---
tutorial/use-built-in
tutorial/customize-factory-reader
```

```{toctree}
---
maxdepth: 2
hidden: true
caption: Reference
---
reference/version-requirements
reference/binary-format
reference/api
```

```{toctree}
---
maxdepth: 2
hidden: true
caption: Examples
---
example/override-streamer
example/read-tobjarray
```
