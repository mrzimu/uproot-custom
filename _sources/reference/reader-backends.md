# Reader backends

Uproot-custom supports two reader backends:

- **C++ backend (default):** fast pybind11 readers built from the bundled C++
  extension. This is the default and is recommended for production workloads
  and large datasets.
- **Python backend:** pure-Python readers in
  `uproot_custom.readers.python`. Use this for rapid development, debugging,
  and when no C++ toolchain is available.

## How backend selection works

`uproot_custom.readers.backend` controls which backend `AsCustom` uses
when materializing readers. **The default value is `"cpp"`**. It can be
changed via:

- The ``UPROOT_CUSTOM_READER_BACKEND`` environment variable (e.g.
  ``UPROOT_CUSTOM_READER_BACKEND=python``).
- ``backend.set("python")`` to set it programmatically.
- ``with backend.use("python"):`` to switch temporarily with a context
  manager.

```python
from uproot_custom.readers import backend

# During development: switch to the Python backend
backend.set("python")

# ... develop, debug, read arrays ...

# Or temporarily switch for a specific block:
with backend.use("python"):
    branch.array()

# For production: use C++ readers (the default)
backend.set("cpp")
```

Set the backend **before** reading branches so that factories
build the correct reader implementations.

```{important}
The default backend is **C++**. When developing a new reader, you should
explicitly use ``backend.set("python")`` or ``with backend.use("python"):``
to use your Python reader. Once the Python reader is validated, port it
to C++ and switch back to the default C++ backend for production.
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

## Writing custom factories for both backends

Start by implementing `build_python_reader` in your factory. Once the reader
logic is validated, implement `build_cpp_reader` to support the default C++
backend. The C++ reader only needs to maintain the same reading logic as the
Python version — porting is a straightforward process.

See the [reader/factory interface](../tutorial/customize-factory-reader/reader-and-factory.md)
for the Python API, and [port readers to C++](../tutorial/customize-factory-reader/port-to-cpp.md)
for the C++ API and pybind11 bindings.

## Troubleshooting

- If you see `Unknown reader backend` errors, ensure the backend is either
  `"cpp"` or `"python"`. Check ``backend.get()``, ``$UPROOT_CUSTOM_READER_BACKEND``
  and any ``backend.set()`` calls.
- If imports fail for C++ readers, either rebuild the
  extension or switch to the Python backend.
