# Write your own reader

This tutorial walks you through implementing a custom `Factory` and reader pair for a ROOT class that Uproot-custom's built-in factories cannot handle — for example, a class that overrides its `Streamer` method or uses an unsupported data layout.

The reader is written for **Detree**, the recommended route for downstream projects: the read path is ordinary Python source, the compiler lowers it to a detree-vm module, and users need neither a C++ toolchain nor a pinned Uproot-custom version.

## What you will build

By the end of this tutorial you will have:

- A **Detree reader** that declares its buffers and decodes the ROOT byte stream.
- A **Python factory** that creates the reader, converts raw arrays into `awkward` arrays, and describes the data layout for lazy evaluation.
- A **registration** step so Uproot picks up your custom code automatically.
- A **debugging loop** that compares the reader's two executors.
- A **package layout** that can be installed by downstream users.

## Prerequisites

```{admonition} Before you begin
---
class: note
---
- Python 3.9+ and a package toolchain (`pip` or `uv`) — a Detree reader needs no compiler and no build step
- A ROOT file that contains the class you want to read, or a way to generate one
```

## Tutorial roadmap

Follow the pages below in order. Each page builds on the previous one:

| Step | Page | What you will learn |
| :--: | ---- | ------------------- |
| 1 | [Investigate your data](investigate-data.md) | Inspect streamer information and raw binary bytes for the class you need to read. |
| 2 | [Write a Detree reader](write-a-reader.md) | Declare the reader, return it from a factory, and read the branch. |
| 3 | [Debug a reader](debug-a-reader.md) | Compile without a file, compare the two executors, and read the common errors. |
| 4 | [Package your project](package-your-project.md) | Set up a Python package that wires your factory and reader together. |

```{tip}
If you are in a hurry, start with **Step 1** to see the byte layout, then **Step 2** for the complete reader and factory. The [Detree reference](../reference/detree-dsl.md) lists every field and the whole compilable subset.
```

## After the tutorial

A Detree reader is not always the right tool. When the read path needs plain Python, or when a branch needs more speed than Detree gives, take the [Python + C++ route](../advanced/index.md): write the reader as a Python `IReader` first, then port it to C++.

```{toctree}
---
maxdepth: 2
hidden: true
---
investigate-data
write-a-reader
debug-a-reader
package-your-project
```
