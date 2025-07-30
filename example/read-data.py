import uproot
import uproot_custom
import my_reader

br = uproot.open("./gen-demo-data/build/demo-data.root")["my_tree"]
br.show(name_width=30, typename_width=30)

print()

arr = br.arrays()
arr.show()
