## Generate demo data

> [!IMPORTANT]
> Make sure you have C++ compiler, `cmake` and `ROOT` installed on your system.

```bash
cd <path/to/uproot-custom>/example/gen-demo-data
mkdir build && cd build
cmake ..
make -j
./gen-data
```

This will generate a file `demo-data.root` in the build directory.

## Install and run the example

```bash
cd <path/to/uproot-custom>/example

# install the example package
pip install -e .

# run the example
python3 read-data.py
```

## Use local `uproot-custom` package

If you want to use the local `uproot-custom` package, you need to build the wheel file first:

```bash
cd <path/to/uproot-custom>
python3 -m build --w -o .cache/dist
```

Then, edit the `pyproject.toml` file in the `example` directory to use the local wheel file:

```toml
requires = ["scikit-build-core>=0.11", "pybind11>=2.10.0", "uproot-custom @ file://path/to/uproot-custom-wheel-file.whl"]
```

where `path/to/uproot-custom-wheel-file.whl` is the path to the wheel file you just built (e.g., `.cache/dist/uproot_custom-0.1.1.dev3+gbf42be4.d20250729-cp311-cp311-linux_x86_64.whl`).

> [!WARNING]
> When the git commit hash of `uproot-custom` changes, the whell file name will also change. You need to update the `pyproject.toml` file accordingly.
