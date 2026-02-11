# Reader backends

Uproot-custom supports two reader backends:

- **C++ backend (default):** fast pybind11 readers built from the bundled C++
  extension. Use this for production workloads.
- **Python backend:** pure-Python readers in `uproot_custom.readers.python`. Use
  it only when you cannot build the C++ extension or when debugging reader
  logic; it is much slower and not suitable for production volumes.

## How backend selection works

`uproot_custom.factories.reader_backend` controls which backend `AsCustom` uses
when materializing readers. The value is read at build time of the factory tree.

```python
import uproot_custom.factories as fac

# Switch to Python readers (slower but compiler-free)
fac.reader_backend = "python"

# ... open files, register target branches, read arrays ...

# Switch back to C++ readers for speed
fac.reader_backend = "cpp"
```

Set the backend **before** opening files or reading branches so that factories
build the correct reader implementations.

```{warning}
The Python backend is intended for development and debugging only. It is
significantly slower than the C++ backend and should not be used for production
or large datasets.
```

## When to use each backend

- Prefer **C++** for any real analysis, performance-sensitive jobs, or large
  datasets.
- Use **Python** only when:
  - You are on a platform without a C++17 toolchain or cannot build the native
    extension.
  - You need to debug reader behavior interactively (e.g., step through Python
    readers or print buffer state) on small samples.

## Writing custom factories for both backends

If you plan to allow the Python backend, your custom factories should implement
both `build_cpp_reader` and `build_python_reader`. See the reader/factory
interface description in [tutorial/customize-factory-reader/reader-and-factory.md](tutorial/customize-factory-reader/reader-and-factory.md).

## Troubleshooting

- If you see `Unknown reader backend` errors, ensure `reader_backend` is either
  `"cpp"` or `"python"`.
- If imports fail for C++ readers (pybind11 module missing), either rebuild the
  extension (e.g., `pip install -e .`) or temporarily switch to the Python
  backend.
