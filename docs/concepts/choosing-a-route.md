# Choosing a technical route

`AsCustom` builds a reader tree for each branch. There are two technical routes for making that tree run a custom reader, and both end at the same factory and the same `awkward` array:

| Route | What you write | What runs the read path | What it costs |
| ----- | -------------- | ----------------------- | ------------- |
| **Detree** (recommended) | a Detree reader: Python source compiled to a detree-vm module | the Detree machine, as bytecode | the read path stays inside the compilable subset |
| **Python + C++** | an `IReader` in Python, then the same logic in C++ | the Python interpreter while developing, native code in production | two implementations to keep in sync, a compiled extension, and version pinning |

The backend values `detree`, `python` and `cpp` are how a route is selected at run time. The Detree route uses `detree`; the Python + C++ route uses `python` while the logic is being developed and `cpp` in production. **`cpp` is the code default**, so a Detree project selects its backend explicitly.

## The Detree route

Write the read path once, in Python source that declares its buffers and sub-readers. The compiler lowers it to a detree-vm module, the module is cached per reader structure, and the machine executes it for every basket. Nothing in the read path runs as Python during a read.

- **One implementation.** There is no second language to port to and no two versions to keep in step.
- **No build step.** `pip install` is the whole installation for downstream users.
- **No ABI coupling.** The reader is compiled at run time, so it does not pin the uproot-custom version, the pybind11 version or the Python ABI.
- **Fast.** The read path is bytecode on a native machine, not interpreted Python.

The cost is flexibility: the read path must stay inside a small compilable subset, listed in the [Detree reference](../reference/detree-dsl.md#the-compilable-subset).

## The Python + C++ route

The Python implementation is not a destination of its own. It runs at Python speed — several times slower than Detree and far slower than C++ — so a branch that matters is ported to C++ before it ships. The Python stage exists because it accepts arbitrary Python and is easy to debug; the C++ stage is what runs in production.

Two consequences follow:

- every reader is written twice and kept in sync, because the Python and C++ implementations must decode the same bytes into the same shape;
- the C++ half is a compiled extension, built against one uproot-custom header, one pybind11 minor version and one Python ABI, so the project pins those versions and rebuilds for each Python release.

Take this route when the read path needs a construct the Detree compiler cannot express, or when a branch is a measurable fraction of the analysis time and Detree is not fast enough.

## What a factory must implement

| Route | While developing | In production |
| ----- | ---------------- | ------------- |
| Detree | `build_detree_reader` | the same method — there is no build step |
| Python + C++ | `build_python_reader` | `build_cpp_reader` |

A factory may implement all three methods. That is how one project serves production users on Detree and keeps a Python implementation for debugging.

## Trade-offs

| | Detree | Python + C++ |
| --- | --- | --- |
| Read path written in | Python, a compilable subset | Python, then C++ |
| Executor | the Detree machine | the Python interpreter, then native code |
| Speed | fast | slowest, then fastest |
| Build step for users | none | compile a pybind11 extension |
| Version pinning | none | uproot-custom minor + pybind11 minor + Python ABI |
| Implementations to maintain | one | two |

See [version requirements](../reference/version-requirements.md) for the versions each route pins.

## Version pinning and the C++ ABI

A C++ reader is compiled against three things that change independently of your project:

- **the uproot-custom C++ header**, whose `IReader` interface is guaranteed compatible only within a minor version;
- **the pybind11 minor version** used to build uproot-custom itself — a mismatch fails at import with `ImportError: generic_type: type "xxx" referenced unknown base type "uproot::IReader"`;
- **the Python ABI**, so a new Python minor version needs a rebuilt extension.

A project on the Python + C++ route therefore pins the exact uproot-custom minor version, pins the pybind11 minor version, and rebuilds for every Python version it supports. The Detree route has none of these requirements.

## Selecting a backend

`uproot_custom.backend` controls which backend `AsCustom` uses when materializing readers. It can be set via:

- The `UPROOT_CUSTOM_READER_BACKEND` environment variable (e.g. `UPROOT_CUSTOM_READER_BACKEND=detree`).
- `set_backend("detree")` to set it programmatically.
- `with use_backend("detree"):` to switch temporarily with a context manager.

```python
import uproot_custom as uc

# Detree route: select the backend, the default is cpp.
uc.set_backend("detree")

# ... read arrays ...
```

The environment variable is read once, when the backend is first needed. Use `set_backend` or `use_backend` to change the selection afterwards.

Set the backend **before** reading branches so that factories build the correct reader implementations.

## Three things called "Python"

The word appears in three different senses, and confusing them is the usual source of "why is my reader slow?":

| Name | What it is |
| ---- | ---------- |
| A **Detree reader** | Python *source* that the compiler lowers to bytecode. It is never interpreted at read time |
| Detree's **Python executor** (`uproot_custom.detree.interp`) | runs the same reader methods as plain Python, for debugging only; it is not a deployment option |
| The **`python` backend** | a separate `IReader` implementation that runs as Python in production; it is the first stage of the Python + C++ route |

So "the reader is written in Python" does not mean "the reader runs as Python". With Detree the source is compiled; with the `python` backend the source is executed.

## No silent fallback

Backend selection is strict. When the selected backend's factory method is not implemented, the first read raises `NotImplementedError`:

```{code-block} console
NotImplementedError: <Factory> does not implement build_detree_reader; use a
different reader backend
```

The failure happens on the first read rather than when the file is opened, because the interpretation and its awkward form are built before the factory is asked for a reader. It is deliberate: a silent switch would make a benchmark, or a bug report, describe a machine that never ran.

## Troubleshooting

- `Unknown reader backend: ...` — set `UPROOT_CUSTOM_READER_BACKEND`, or call `set_backend`, with one of `"detree"`, `"python"`, or `"cpp"`.
- `NotImplementedError: ... does not implement build_detree_reader` — add `build_detree_reader` to the factory, or take the Python + C++ route.
- If imports fail for C++ readers, either rebuild the extension or select another backend.
