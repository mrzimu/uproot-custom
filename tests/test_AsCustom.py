from pathlib import Path

import uproot
import uproot_custom


uproot_custom.AsCustom.target_branches |= {
    "/my_tree:my_obj/m_carr_vec_int[3]",
    "/my_tree:my_obj/m_int",
    "/my_tree:my_obj/m_carr_tstring[3]",
    "/my_tree:my_obj/m_carr2d_vec_int[2][3]",
    "/my_tree:my_obj/m_carr2d_tstring[2][3]",
    "/my_tree:complicated_stl/m_arr_vec_int[5]",
    "/my_tree:complicated_stl/m_vec_uset_int",
    "/my_tree:complicated_stl/m_vec_list_int",
    "/my_tree:complicated_stl/m_list_set_int",
}


def test_AsCustom_1():
    f = uproot.open(Path(__file__).parent / "test-data-1.root")
    tree = f["my_tree"]
    arr = tree.arrays()


def test_AsCustom_2():
    f = uproot.open(Path(__file__).parent / "test-data-2.root")
    tree = f["my_tree"]
    tree["complicated_stl/m_arr_vec_int[5]"].array()
    tree["complicated_stl/m_vec_uset_int"].array()
    tree["complicated_stl/m_vec_list_int"].array()
    tree["complicated_stl/m_list_set_int"].array()
