# Customize Reader & Factory

This tutorial walks you through implementing a custom `Factory` and `Reader`
pair for a ROOT class that uproot-custom's built-in factories cannot handle —
for example, a class that overrides its `Streamer` method or uses an
unsupported data layout.

```{important}
The default reader backend is **C++**. During development, you must explicitly
set `uproot_custom.factories.reader_backend = "python"` to use your Python
reader. Once the Python reader is validated, port it to C++ and switch back to
the default C++ backend.
```

## What you will build

By the end of this tutorial you will have:

- A **Python reader** that decodes binary data from the ROOT byte buffer.
- A **Python factory** that creates the reader, converts raw arrays into
  `awkward` arrays, and describes the data layout for `dask`.
- A **registration** step so Uproot picks up your custom code automatically.
- A **C++ reader** for production-level performance.

## Prerequisites

```{admonition} Before you begin
---
class: note
---
- A Python toolchain capable of building Python packages (e.g. `pip`,
  `setuptools`, `scikit-build-core`)
- **C++17 compatible compiler** (e.g., GCC ≥ 7, Clang ≥ 5, MSVC ≥ 19.15) for building C++ readers
- CMake ≥ 3.20 for building native extensions
```

## Tutorial roadmap

Follow the pages below in order. Each page builds on the previous one:

| Step | Page | What you will learn |
| :--: | ---- | ------------------- |
| 1 | [Pipeline overview](customize-factory-reader/pipeline.md) | Understand the 5-stage pipeline and see a complete end-to-end example. |
| 2 | [Investigate your data](customize-factory-reader/investigate-data.md) | Inspect streamer information and raw binary bytes for the class you need to read. |
| 3 | [Reader & factory interface](customize-factory-reader/reader-and-factory.md) | Learn the Python `IReader` and `Factory` APIs, then study a full worked example (`TArray`). |
| 4 | [Project setup](customize-factory-reader/project-setup.md) | Set up a Python package that wires your factory and reader together. |
| 5 | [Port readers to C++](customize-factory-reader/port-to-cpp.md) | Port the reader logic to C++ for production speed. |

```{tip}
If you are in a hurry, start with **Step 1** to see the big picture and a
complete minimal example you can adapt. Then jump to **Step 4** to set up
your project and fill in the details using the API reference in **Step 3**.
```

```{toctree}
---
maxdepth: 2
hidden: true
---
customize-factory-reader/pipeline
customize-factory-reader/investigate-data
customize-factory-reader/reader-and-factory
customize-factory-reader/project-setup
customize-factory-reader/port-to-cpp
```
