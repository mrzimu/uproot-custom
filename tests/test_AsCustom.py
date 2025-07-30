from pathlib import Path

import uproot
import uproot_custom


uproot_custom.AsCustom.target_branches |= {
    "/my_tree:my_obj/m_carr_vec_int[3]",
    "/my_tree:my_obj/m_int",
    "/my_tree:my_obj/m_carr_tstring[3]",
    "/my_tree:my_obj/m_carr2d_vec_int[2][3]",
    "/my_tree:my_obj/m_carr2d_tstring[2][3]",
}


def test_AsCustom():
    f = uproot.open(Path(__file__).parent / "test-data.root")
    br = f["my_tree"]
    arr = br.arrays()
