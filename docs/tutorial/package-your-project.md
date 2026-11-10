# Package your project

A Detree reader needs no build step: the reader is Python source, and the installed Detree machine compiles it the first time the branch is read. A downstream project is therefore an ordinary Python package.

## Project layout

A ready-to-use template is available in the [example repository](https://github.com/mrzimu/uproot-custom-example). Download the [source archive](https://github.com/mrzimu/uproot-custom-example/archive/refs/tags/v0.1.0.tar.gz), unzip, and rename the root directory to match your project name.

A Detree-only project needs three things:

```
my_project/
    ├── pyproject.toml
    └── my_module/
        ├── __init__.py       # registers the factories and target branches
        ├── factories.py      # Factory subclasses
        └── readers.py        # @reader classes
```

Readers must live in a `.py` file inside an importable module: the compiler re-reads their source, so a reader defined in a notebook or a REPL is refused. Splitting readers and factories into separate modules is a convention, not a requirement.

If you later add [C++ readers](../advanced/cpp-reader.md), the package grows a `cpp/` directory and a build backend; the Python modules stay as they are.

## Create a virtual environment

```bash
cd /path/to/your/project
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

## Install in editable mode

```bash
pip install -e .
```

Python changes take effect immediately. If you have C++ sources, re-run `pip install -e .` to rebuild the extension module after modifying them.

## Registration checklist

1. **Investigate your data** — inspect streamer information and binary bytes as described in [](investigate-data.md). Pay special attention to headers, base-class layout, and any custom `Streamer` logic.

2. **Survey built-in code** — review the built-in factories and readers in Uproot-custom for patterns you can reuse or subclass.

3. **Implement** — write your `Factory` and `@reader` classes following [](write-a-reader.md).

4. **Register** — obtain the regularized object-path of the target branch and add it to `uproot_custom.AsCustom.target_branches` before that branch's interpretation is first computed (see [get started](../getting-started.md#step-2-register-the-branch)). Registering at import time, in `__init__.py`, is the usual place.

5. **Select the backend** — the code default is `cpp`, so call `uproot_custom.set_backend("detree")` (or set `UPROOT_CUSTOM_READER_BACKEND=detree`), next to the registration.

## Building a C++ reader

Only the [C++ path](../advanced/cpp-reader.md) needs a compiler and a build backend.

```{warning}
If using C++ readers, pin **exact** versions of Uproot-custom and `pybind11` in `pyproject.toml` to avoid build-time incompatibilities. `pybind11` is a **build-only** dependency — do not import it at runtime, or reader loading may fail. See [](../reference/version-requirements.md) for details.
```

```{admonition} Next step
---
class: hint
---
With the package in place, read a branch and check the result with the [debugging loop](debug-a-reader.md).
```
