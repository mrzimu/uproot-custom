# Version requirements

## Uproot-custom versioning

Uproot-custom gurantees C++ header compatibility with same minor versions (e.g. C++ headers in `2.0.0` and `2.0.1` are compatible). Therefore, users' project should specify specific minor versions of uproot-custom in their `pyproject.toml` file to avoid unexpected incompatibility issues.

## pybind11 version requirement

If the version of `pybind11` differs between the one used to build uproot-custom and the one used to build user's C++ readers, an exception like below may be raised when importing the user's C++ extension module:

```
ImportError: generic_type: type "xxx" referenced unknown base type "uproot::IReader"
```

To avoid this issue, every versions of uproot-custom requires users to build their C++ readers with the same minor version of `pybind11` as the one used to build uproot-custom. Users are expected to specify the exact version of `pybind11` manually in their `pyproject.toml` file.

## Summary table

This table summarizes the required `pybind11` versions for each uproot-custom version:

| uproot-custom | pybind11 |
| :-----------: | :------: |
| `2.0`         | `3.0`    |
