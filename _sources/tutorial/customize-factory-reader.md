# Customize factory and reader

If the built-in factories cannot reach your needs, you can implement your own
`factory` and/or `reader`.

```{admonition} Prerequisites
---
class: note
---
Custom readers require a C++17 compiler, `CMake>3.20`, and a Python toolchain
able to build extension modules.
```

What you'll find here:
- How streamer info maps to factories/readers.
- How to inspect binary payloads before coding.
- A template Python project that wires Python factories to C++ readers.

Recommended flow: read **Bootstrap**, skim **Streamer information** and
**Binary data**, then dive into **Reader and factory interface** before using
the **Template Python project**.

```{toctree}
---
maxdepth: 2
hidden: true
---
customize-factory-reader/bootstrap
customize-factory-reader/streamer-info
customize-factory-reader/binary-data
customize-factory-reader/reader-and-factory
customize-factory-reader/template-python-project
```
