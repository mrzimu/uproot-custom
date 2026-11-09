# Reader backends

`AsCustom` builds a reader tree for each branch; the **reader backend** decides
which implementation of that tree reads the bytes. Four backends are available:

| Backend | Factory method | Reader implementation | Notes |
| ------- | -------------- | --------------------- | ----- |
| `cpp` | `build_cpp_reader` | pybind11 readers in `uproot_custom.cpp` | **Default**; recommended for production |
| `python` | `build_python_reader` | pure-Python readers in `uproot_custom.python` | Development, debugging, no C++ toolchain |
| `detree` | `build_detree_reader` | declarative readers in `uproot_custom.detree` | Compiles to a detree-vm module; experimental, optional dependency |
| `forth` | `build_forth_reader` | Forth readers in `uproot_custom._forth` | Development and benchmarking only; warns on use |

## How backend selection works

`uproot_custom.backend` controls which backend `AsCustom` uses when
materializing readers. **The default value is `"cpp"`.** It can be changed via:

- The `UPROOT_CUSTOM_READER_BACKEND` environment variable (e.g.
  `UPROOT_CUSTOM_READER_BACKEND=python`).
- `set_backend("python")` to set it programmatically.
- `with use_backend("python"):` to switch temporarily with a context manager.

```python
import uproot_custom as uc

# During development: switch to the Python backend
uc.set_backend("python")

# ... develop, debug, read arrays ...

# Or temporarily switch for a specific block:
with uc.use_backend("python"):
    branch.array()

# For production: use C++ readers (the default)
uc.set_backend("cpp")
```

The environment variable is read once, when the backend is first needed. Use
`set_backend` or `use_backend` to change the selection afterwards.

Set the backend **before** reading branches so that factories build the
correct reader implementations.

```{important}
The default backend is **C++**. When developing a new reader, explicitly use
`uc.set_backend("python")` or `with uc.use_backend("python"):` to use your
Python reader. Once the Python reader is validated, port it to C++ and switch
back to the default C++ backend for production.
```

## When to use each backend

- Use **Python** when:
  - You are developing and prototyping new readers.
  - You need to debug reader behavior interactively (e.g., step through Python
    readers or print stream state).
  - You are on a platform without a C++17 toolchain or cannot build the native
    extension.
- Prefer **C++** for any real analysis, performance-sensitive jobs, or large
  datasets.
- Use **detree** to experiment with the compiled reader path; see
  [the Detree reader backend](detree-stack.md). It is optional and experimental.
- Use **forth** only for development or benchmarking. It is not recommended for
  production and emits a `UserWarning` on every read.

## Writing custom factories for multiple backends

Start by implementing `build_python_reader` in your factory. Once the reader
logic is validated, implement `build_cpp_reader` to support the default C++
backend. The C++ reader only needs to maintain the same reading logic as the
Python version — porting is a straightforward process. Implement
`build_detree_reader` only if the branch should also be readable with the
detree backend.

See the [reader/factory interface](../tutorial/customize-factory-reader/reader-and-factory.md)
for the Python API, and [port readers to C++](../tutorial/customize-factory-reader/port-to-cpp.md)
for the C++ API and pybind11 bindings.

## Troubleshooting

- `Unknown reader backend: ...` — set `UPROOT_CUSTOM_READER_BACKEND`, or call
  `set_backend`, with one of `"cpp"`, `"python"`, `"forth"`, or `"detree"`.
- `NotImplementedError: ... does not build a native reader` — the factory does
  not implement `build_detree_reader`; use another backend or add a native
  reader.
- If imports fail for C++ readers, either rebuild the extension or switch to
  the Python backend.
