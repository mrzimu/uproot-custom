# The Python + C++ route

Detree is the recommended route: one reader, written in Python source, compiled at run time, with no build step and no version pinning. This section documents the other one, in which a branch is decoded by an `IReader` written twice — once in Python, then again in C++.

Read [choosing a technical route](../concepts/choosing-a-route.md) first; the trade-offs below are the short version.

## Why take this route

Two reasons, and only two:

- **The read path needs plain Python.** A construct outside the [compilable subset](../reference/detree-dsl.md#the-compilable-subset) — a `try`, a lookup into a dictionary keyed by a name read from the file, a call into another package — cannot be expressed as a Detree reader.
- **Detree is not fast enough.** The branch is a measurable fraction of the analysis time, and the last factor of speed matters more than the cost listed below.

## How the route works

The route has two stages, and they must stay in step:

1. **[The Python implementation](python-reader.md)** — an `IReader` whose `read` is ordinary Python. It accepts anything Python can do, needs no build step, and runs at Python speed. This is where the logic is worked out and debugged.
2. **[The C++ implementation](cpp-reader.md)** — the same fields in the same order, written in C++, compiled into a pybind11 extension. This is what runs in production.

Both stages share one factory: `build_python_reader` returns the first, `build_cpp_reader` returns the second, and `make_awkward_content` / `make_awkward_form` are written once. Only the stage matching the selected backend runs.

```{important}
The Python stage is not a deployment target. It is several times slower than Detree, so a project on this route is expected to finish the port to C++ before it ships. The Python implementation stays in the repository as the readable statement of the byte layout and as a debugging oracle.
```

## What it costs

- **Two implementations.** The Python and C++ readers must decode the same bytes into the same `data()` shape; nothing checks that beyond your tests.
- **A build step for users.** The extension is compiled per platform and per Python version.
- **Version pinning.** The C++ header is compatible only within one uproot-custom minor version, the pybind11 minor version must match, and each Python ABI needs a rebuild. See [version requirements](../reference/version-requirements.md).

## The two stages

```{toctree}
---
maxdepth: 2
hidden: true
---
python-reader
cpp-reader
```
