# Reader backends

Uproot-custom supports two reader backends:

- **C++ backend (default):** fast pybind11 readers built from the bundled C++
  extension. This is the default and is recommended for production workloads
  and large datasets.
- **Python backend:** pure-Python readers in
  `uproot_custom.readers.python`. Use this for rapid development, debugging,
  and when no C++ toolchain is available.

## How backend selection works

`uproot_custom.factories.reader_backend` controls which backend `AsCustom` uses
when materializing readers. **The default value is `"cpp"`**. The value is
read at build time of the factory tree.

```python
import uproot_custom.factories as fac

# During development: switch to the Python backend
fac.reader_backend = "python"

# ... develop, debug, read arrays ...

# For production: use C++ readers (the default)
fac.reader_backend = "cpp"
```

Set the backend **before** opening files or reading branches so that factories
build the correct reader implementations.

```{important}
The default backend is **C++**. When developing a new reader, you must
explicitly set `fac.reader_backend = "python"` to use your Python reader.
Once the Python reader is validated, port it to C++ and switch back to the
default C++ backend for production.
```

## When to use each backend

- Use **Python** when:
  - You are developing and prototyping new readers.
  - You need to debug reader behavior interactively (e.g., step through Python
    readers or print buffer state).
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

- If you see `Unknown reader backend` errors, ensure `reader_backend` is either
  `"cpp"` or `"python"`.
- If imports fail for C++ readers (pybind11 module missing), either rebuild the
  extension (e.g., `pip install -e .`) or switch to the Python backend.
