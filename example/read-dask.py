from pathlib import Path

import my_reader
import uproot

import uproot_custom

fpath = Path(__file__).parent.parent / "tests" / "test-data.root"

# Override streamer
dak_override_streamer = uproot.dask({fpath: "/my_tree/override_streamer"})

dak_override_streamer.compute().show()

print()

# Object with TObjArray
dak_obj_with_obj_array = uproot.dask({fpath: "/my_tree/obj_with_obj_array/m_obj_array"})
dak_obj_with_obj_array.compute().show()
