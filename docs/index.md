# Introduction

[`uproot`](https://uproot.readthedocs.io/en/latest/basic.html) can already read some custom classes directly from `TTree`. However, in some cases, custom classes are too complex for `uproot` to read, such as when their `Streamer` methods are overridden or some specific data members are not supported by `uproot`.

To read such classes, `uproot-custom` privides a `Reader` interface, so that you can read them with your own `Reader`. The `Reader` interface defines how to read the data members of a class from the binary stream and how to structure the data in Python.

`uproot-custom` does not provide a full reimplementation of `ROOT`'s I/O system. Users are expected to implement their own `Reader` for their custom classes, or for classes that built-in readers cannot handle.

```{toctree}
---
maxdepth: 2
hidden: true
---
get-started
concepts
```

```{toctree}
---
maxdepth: 2
hidden: true
caption: Further Reading
---
```

```{toctree}
---
maxdepth: 2
hidden: true
caption: Developer Guide
---
```
