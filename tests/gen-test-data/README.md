# gen-test-data

This program generates test data for the uproot-custom package. The generated data is stored in the `tests/data` directory.

## Requirements

- ROOT
- CMake
- C++ compiler

## Usage

To generate the test data, run the following commands in the terminal:

```bash
cd /path/to/gen-test-data
mkdir build
cd build
cmake ..
make -j
./gen-test-data
```

This will generate a series of data files in the `build` directory. You can then move these files to the `tests/data` directory of the uproot-custom package for use in testing.
