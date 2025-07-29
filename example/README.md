## Run this example

### Generate demo data

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

### Install and run the example

> [!IMPORTANT]
> Make sure you are in the python virtual environment where `uproot-custom` is installed.

```bash
cd <path/to/uproot-custom>/example

# install the example package
pip install -e .

# run the example
python3 read-data.py
```
