from uproot_custom import registered_readers, AsCustom

from .OverrideStreamerReader import OverrideStreamerReader

AsCustom.target_branches |= {
    "/my_tree:override_streamer",
    "/my_tree:complicated_stl/m_arr_vec_int[5]",
    "/my_tree:complicated_stl/m_vec_uset_int",
    "/my_tree:complicated_stl/m_vec_list_int",
    "/my_tree:complicated_stl/m_list_set_int",
}

registered_readers.add(OverrideStreamerReader)
