# Project setup

Uproot-custom readers start with Python factories and Python readers. Once
validated, the reader logic is ported to C++ for production performance.
A proper Python project is the recommended approach.

A ready-to-use template is available in the
[example repository](https://github.com/mrzimu/uproot-custom-example).
Download the
[source archive](https://github.com/mrzimu/uproot-custom-example/archive/refs/tags/v0.1.0.tar.gz),
unzip, and you will see:

```
uproot-custom-example-0.1.0/
    ├── pyproject.toml
    ├── README.md
    ├── my_reader/          # Python factories and readers
    │   └── ...
    └── cpp/                # C++ readers (for production performance)
        └── ...
```

Rename the root directory to match your project name.

```{warning}
If using C++ readers, pin **exact** versions of uproot-custom and `pybind11`
in `pyproject.toml` to avoid build-time incompatibilities. `pybind11` is a
**build-only** dependency — do not import it at runtime, or reader loading may
fail. See [](../../reference/version-requirements.md) for details.
```

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

Python changes take effect immediately. If you have C++ sources, re-run
`pip install -e .` to rebuild the extension module after modifying them.

## Implementation checklist

1. **Investigate your data** — inspect streamer information and binary bytes as
   described in [](investigate-data.md). Pay special attention to headers,
   base-class layout, and any custom `Streamer` logic.

2. **Survey built-in code** — review the built-in factories and readers in
   uproot-custom for patterns you can reuse or subclass.

3. **Implement** — write your `Factory` and `Reader` in Python,
   following the interfaces described in [](reader-and-factory.md).
   Then [port the reader to C++](port-to-cpp.md) for production use.

4. **Register** — obtain the regularized object-path of the target branch and
   add it to `uproot_custom.AsCustom.target_branches` **before** opening the
   file.

---

```{admonition} Next step
---
class: hint
---
Once your Python reader is working, the final step is to
[port it to C++](port-to-cpp.md) for production-level performance.
```
