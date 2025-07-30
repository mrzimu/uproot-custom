from uproot_custom import BaseReader

from . import my_reader_cpp as _cpp
import awkward.contents


class OverrideStreamerReader(BaseReader):
    @classmethod
    def gen_tree_config(
        cls,
        top_type_name: str,
        cls_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str = "",
    ):
        fName = cls_streamer_info["fName"]
        if fName != "TOverrideStreamer":
            return None

        return {
            "reader": cls,
            "name": fName,
        }

    @classmethod
    def get_cpp_reader(cls, tree_config):
        if tree_config["reader"] is not cls:
            return None

        return _cpp.OverrideStreamerReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        int_array, double_array = raw_data

        return awkward.contents.RecordArray(
            [
                awkward.contents.NumpyArray(int_array),
                awkward.contents.NumpyArray(double_array),
            ],
            ["m_int", "m_double"],
        )
