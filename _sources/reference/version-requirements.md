# Version requirements

## Uproot-custom versioning

Uproot-custom guarantees C++ header compatibility within a minor version (for
example, `2.0.0` and `2.0.1` headers are compatible). Pin the minor version in
your `pyproject.toml` to avoid surprises when rebuilding readers.

## pybind11 version requirement

`pybind11` is a **build-time dependency only**. Do not ship or import
`pybind11` in the runtime environment; having `pybind11` present at runtime can
trigger unexpected errors when loading readers. Build with the matching version
and keep it out of the deployed environment.

If the version of `pybind11` differs between the one used to build uproot-custom
and the one used to build your C++ readers, an exception like below may be
raised when importing your extension module:

```
ImportError: generic_type: type "xxx" referenced unknown base type "uproot::IReader"
```

To avoid this issue, build your C++ readers with the same minor version of
`pybind11` that was used to build uproot-custom. Specify the exact version of
`pybind11` in your `pyproject.toml`, then ensure `pybind11` is absent from the
runtime environment after build.

Quick check:
- `python -c "import uproot_custom, pybind11; print(uproot_custom.__version__, pybind11.__version__)"`
- Ensure both minor versions match; if not, pin `pybind11` and rebuild your
	reader module.

## Summary table

This table summarizes the required `pybind11` versions for each uproot-custom version:

| uproot-custom | pybind11 |
| :-----------: | :------: |
| `2.0`         | `3.0`    |
| `2.1`         | `3.0`    |
| `2.2`		    | `3.0`    |
