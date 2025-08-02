import uproot
import uproot_custom
import my_reader

tree = uproot.open("./gen-demo-data/build/demo-data.root")[
    "my_tree"
]
tree.show(name_width=30, typename_width=30)

print()

arr = tree.arrays()
arr.show()
