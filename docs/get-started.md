# Get started

## Predefined reading rules

If your custom class is just too complex for `uproot` to read, you can try to use the predefined reading rules provided by `uproot-custom`.

`uproot-custom` needs to know which branch you want to read. You need to firstly obtain the branch path of your custom class in the `TTree`.

```python
import uproot
import uproot_custom

file = uproot.open("my_file.root")
branch = file["path/to/my-branch"]
print(uproot_custom.regularize_object_path(branch.object_path))
```

This will print the regularized path of the branch, like `/tree:path/to/my-branch`. You can then register this path to `uproot_custom.AsCustom`:

```python
import uproot
import uproot_custom

# Register the branch path obtained above
uproot_custom.AsCustom.target_branches.add("/tree:path/to/my-branch")

file = uproot.open("my_file.root")
branch = file["path/to/my-branch"]
branch.show()
array = branch.array()
```

In `branch.show()`, you should be able to see the interpretation becomes to `AsCustom(...)`, which means `uproot-custom` will try to read this branch with the predefined reading rules. In `branch.array()`, you should get an `awkward` array containing the data of your custom class.

```{note}
Sometimes `ROOT` will decompose a custom class into multiple branches. You need to obtain paths of all branches that you want to read.
```

## Customized reading rules

If the predefined reading rules cannot handle your custom class, you can implement your own `Reader` to read it. Before continuing, you should take a view at [basic concepts](concepts).

[The example project](https://github.com/mrzimu/uproot-custom/tree/main/example) provides a good entry point to start.

```{note}
Customizing reading rules requires a C++ compiler and `CMake` installed on your system.
```

### Step 1: Create your Python project

<!-- TODO: Attach an example project in release -->

Copy the example project to your local machine.

(get-started-custom-step2)=
### Step 2: Implement C++ part of your reader

Enter to `<your-project>/cpp` directory, define C++ part of your own reader:

- Inherits from `uproot::IElementReader`.

- `void read( uproot::BinaryBuffer& buffer )` reads data from the binary stream. You should implement your reading logics here and store data into the `std::vector`.

- `pybind11::object data() const` returns the data you've stored in the `std::vector`. You should transfer them into numpy array via `uproot::make_array` function.

### Step 3: Implement Python part of your reader

Enter to `<your-project>/my_reader` directory, define Python part of your own reader: 

- Inherits from `uproot_custom.BaseReader`.

- `gen_tree_config` identifies whether current node in the data tree is suitable for your reader.

- `get_cpp_reader` reads node configuration generated in `gen_tree_config` and creates your C++ reader [defined above](#get-started-custom-step2).

- `reconstruct_array` reconstructs raw data returned from your C++ reader. Usually C++ reader only return `list`, `tuple` and numpy array. You should transform these data into an awkward array in this method.

```{tip}
You can refer to [predefined readers](https://github.com/mrzimu/uproot-custom/tree/main/uproot_custom/readers.py) for more details about how to implement your own reader.
```

### Step 4: Register your reader to `uproot_custom.AsCustom`

To let `uproot_custom.AsCustom` knows your reader, add these lines:

```python
import uproot_custom
from xxx import MyReader # xxx refers to your project

uproot_custom.registered_readers.add(MyReader)
```

### Step 5: Register the target branch

Follows steps in [](#predefined-reading-rules) to register the branch you want to read.
