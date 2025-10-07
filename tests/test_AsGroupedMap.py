import pytest
import uproot

import uproot_custom

as_grouped_map_branches = [
    "/my_tree:nested_stl/m_map3_str/m_map3_str.first",
    "/my_tree:nested_stl/m_map3_str/m_map3_str.second",
    "/my_tree:nested_stl/m_map_vec_obj/m_map_vec_obj.first",
    "/my_tree:nested_stl/m_map_vec_obj/m_map_vec_obj.second",
    "/my_tree:nested_stl/m_map_vec_str/m_map_vec_str.first",
    "/my_tree:nested_stl/m_map_vec_str/m_map_vec_str.second",
    "/my_tree:complicated_stl/m_map_vec_int/m_map_vec_int.first",
    "/my_tree:complicated_stl/m_map_vec_int/m_map_vec_int.second",
    "/my_tree:complicated_stl/m_umap_list_int/m_umap_list_int.first",
    "/my_tree:complicated_stl/m_umap_list_int/m_umap_list_int.second",
    "/my_tree:complicated_stl/m_map_set_int/m_map_set_int.first",
    "/my_tree:complicated_stl/m_map_set_int/m_map_set_int.second",
    "/my_tree:complicated_stl/m_umap_uset_int/m_umap_uset_int.first",
    "/my_tree:complicated_stl/m_umap_uset_int/m_umap_uset_int.second",
    "/my_tree:complicated_stl/m_map_vec_list_set_int/m_map_vec_list_set_int.first",
    "/my_tree:complicated_stl/m_map_vec_list_set_int/m_map_vec_list_set_int.second",
]

uproot_custom.AsGroupedMap.target_branches |= set(as_grouped_map_branches)


@pytest.mark.parametrize("sub_branch_path", as_grouped_map_branches)
def test_AsGroupedMap_array(f_test_data, sub_branch_path):
    f_test_data[sub_branch_path].array()


@pytest.mark.parametrize("sub_branch_path", as_grouped_map_branches)
def test_AsGroupedMap_dask(test_data_path, sub_branch_path):
    uproot.dask({test_data_path: sub_branch_path}).compute()
