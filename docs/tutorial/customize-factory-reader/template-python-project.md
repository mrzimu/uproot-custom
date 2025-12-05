# Template Python project

Since uproot-custom is implemented with both Python and C++, it is recommended to create a Python project to help manage the dependencies and build process.

A template project can be found in the [example repository](https://github.com/mrzimu/uproot-custom-example). Download the repository [source code](https://github.com/mrzimu/uproot-custom-example/archive/refs/tags/v0.1.0.tar.gz), unzip it, you should see a directory structure like this:

```
uproot-custom-example-0.1.0/
    ├── pyproject.toml
    ├── README.md
    ├── my_reader/
    │   └── Python source files...
    └── cpp/
        └── C++ source files...
```

You can rename the root directory `uproot-custom-example-0.1.0` to your project name.

```{warning}
Users should specify exact versions of uproot-custom and `pybind11` in the `pyproject.toml` file to avoid unexpected incompatibility issues. See [version requirements](../../reference/version-requirements.md) for more details.
```

## Create virtual environment and install the project

Create a Python virtual environment in the root directory of your project, and activate it:

```bash
cd /path/to/your/project
python -m venv .venv
source .venv/bin/activate # On Windows use: .venv\Scripts\activate
```

Install the project in editable mode:

```bash
pip install -e .
```

Any change in the Python source files will be reflected immediately, but changes in the C++ source files require rebuilding the extension by running `pip install -e .` again.

## Implement your own factory and reader

You can now implement your own `factory` in the `my_reader` directory, and your own `reader` in the `cpp` directory. For summary, here is a checklist of what you need to do:

1. Invetigate the streamer information and binary format of your custom class. It is recommended to take a view at the binary data stored in the file, as explained in [](obtain-binary-data).

2. Look through the built-in factories/readers in uproot-custom, design your own `factory`/`reader` based on them.

3. Implement your own `factory` in Python, and `reader` in C++.

4. Obtain the regularized object path of the branch you want uproot-custom to interpret, add it to the `uproot_custom.AsCustom.target_branches`.
