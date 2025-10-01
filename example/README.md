This is an example project that demonstrates how to implement your own `factory` and `reader` to read your custom classes stored in ROOT files using `uproot-custom`.

> [!NOTE]
> This is also a test project for `uproot-custom`.

## Install and run the example

You need to install the example project first:

```bash
cd <path/to/uproot-custom>/example

# install the example package
pip install -e .
```

Then you can run the example script:

```bash
# run the example
python3 read-data.py
```

For dask example, you need to install `dask` and `dask-awkward` first:

```bash
# install dask and dask-awkward
pip install "dask[complete] dask-awkward"

# run the dask example
python3 dask-read-data.py
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

If you have already installed the `uproot-custom` package, firstly uninstall it:

```bash
pip uninstall uproot-custom
```

Then reinstall the example package:

```bash
cd <path/to/uproot-custom>/example
pip install -e .
```

> [!WARNING]
> When the git commit hash of `uproot-custom` changes, the wheel file name will also change. You need to update the `pyproject.toml` file accordingly.

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
