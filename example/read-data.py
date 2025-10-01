import uproot
import uproot_custom
import my_reader

tree = uproot.open("./gen-demo-data/build/demo-data.root")["my_tree"]

b_override_streamer = tree["override_streamer"]
b_override_streamer.show(name_width=60, typename_width=40)
override_streamer_array = b_override_streamer.array()
print()
print("Array of override_streamer:")
override_streamer_array.show()
print()

b_obj_with_obj_array = tree["obj_with_obj_array/m_obj_array"]
b_obj_with_obj_array.show(name_width=60, typename_width=40)
obj_with_obj_array = b_obj_with_obj_array.array()
print()
print("obj_with_obj_array:")
obj_with_obj_array.show()
