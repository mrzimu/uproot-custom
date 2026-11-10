# Version requirements

What each backend needs from the environment, and what a downstream project must pin.

## Python

Uproot-custom requires **Python 3.9 – 3.14**. `awkward`, `numpy`, `uproot` and `detree-vm` are regular runtime dependencies; `pybind11` is not.

## The Detree route

Nothing beyond the package itself. A Detree reader is Python source that the installed Detree machine compiles at run time, so:

- there is no compiler, CMake or build step;
- the reader does not depend on the Uproot-custom version it was written against — the module is compiled from the reader's structure at import time and cached per process;
- the reader does not depend on the Python version in any way that needs a rebuild, because the read path is compiled to detree-vm module bytes and executed by the machine.

The `detree-vm` release that Uproot-custom depends on ships the Rust machine. The Python and C++ machines exist for development and testing and are not selectable through the public API.

## The Python + C++ route

The Python implementation needs nothing beyond the package, exactly like Detree. The C++ implementation is the only part of the project with a build-time contract, and everything below applies to it and to nothing else — see [stage 2](../advanced/cpp-reader.md).

### Compiler

Uproot-custom and user-implemented C++ readers require a **C++17 compatible compiler**. The CMake configuration sets `CMAKE_CXX_STANDARD 17`. Ensure your compiler supports C++17 features such as structured bindings, `std::optional`, `std::variant`.

If you are building on an older system, you may need to upgrade your compiler (e.g., GCC ≥ 7, Clang ≥ 5, MSVC ≥ 19.15) or adjust the CMake flags accordingly.

### pybind11 and the ABI

`pybind11` is a **build-time dependency only**. Do not ship or import `pybind11` in the runtime environment; having `pybind11` present at runtime can trigger unexpected errors when loading readers. Build with the matching version and keep it out of the deployed environment.

The extension is compiled against three things that move independently of your project:

| Coupled to | Compatibility |
| ---------- | ------------- |
| the Uproot-custom C++ header (`uproot-custom.hh`) | guaranteed only within one minor version, e.g. `2.0.0` and `2.0.1` |
| the `pybind11` minor version used to build Uproot-custom | must match; otherwise the module fails at import |
| the Python ABI | a new Python minor version needs a rebuilt extension |

A mismatch is not subtle. The Python-visible base type fails to resolve at import:

```
ImportError: generic_type: type "xxx" referenced unknown base type "uproot::IReader"
```

To avoid it, build your C++ readers with the same minor version of `pybind11` that was used to build Uproot-custom. Specify the exact version of `pybind11` in your `pyproject.toml`, then ensure `pybind11` is absent from the runtime environment after build.

Quick check:
- `python -c "import uproot_custom, pybind11; print(uproot_custom.__version__, pybind11.__version__)"`
- Ensure both minor versions match; if not, pin `pybind11` and rebuild your reader module.

### Pinning

A project that ships C++ readers pins both versions:

- pin Uproot-custom to a minor version (for example `uproot-custom==2.5.*`) — the header is compatible within it;
- pin `pybind11` to the matching minor version;
- rebuild the wheel for each Python version you publish.

A project that ships only Detree readers pins nothing for this reason; see [choosing a technical route](../concepts/choosing-a-route.md).

## Summary

| Route | Build step | Version pinning |
| ----- | ---------- | --------------- |
| Detree | none | none |
| Python + C++ | C++17 compiler, CMake, pybind11 | uproot-custom minor + pybind11 minor + Python ABI |

This table summarizes the required `pybind11` versions for each Uproot-custom version:

| Uproot-custom | pybind11 |
| :-----------: | :------: |
| `2.*`         | `3.0.*`  |
