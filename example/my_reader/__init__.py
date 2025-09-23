from uproot_custom import registered_readers, AsCustom, AsGroupedMap

from .OverrideStreamerReader import OverrideStreamerReader

AsCustom.target_branches |= {
    "/my_tree:override_streamer",
    "/my_tree:complicated_stl/m_arr_str[5]",
    "/my_tree:complicated_stl/m_arr_vec_int[5]",
    "/my_tree:complicated_stl/m_carr_vec_int[5]",
    "/my_tree:complicated_stl/m_carr_str[5]",
    "/my_tree:complicated_stl/m_vec_uset_int",
    "/my_tree:complicated_stl/m_arr_map_int_double[5]",
    "/my_tree:complicated_stl/m_carr_map_int_double[5]",
}

AsGroupedMap.target_branches |= {
    "/my_tree:complicated_stl/m_map_vec_int/m_map_vec_int.second",
    "/my_tree:complicated_stl/m_umap_list_int/m_umap_list_int.second",
    "/my_tree:complicated_stl/m_map_set_int/m_map_set_int.second",
    "/my_tree:complicated_stl/m_umap_uset_int/m_umap_uset_int.second",
    "/my_tree:complicated_stl/m_map_vec_list_set_int/m_map_vec_list_set_int.second",
}

registered_readers.add(OverrideStreamerReader)
