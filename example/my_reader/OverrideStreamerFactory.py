from uproot_custom import BaseFactory

from . import my_reader_cpp as _cpp
import awkward.contents


class OverrideStreamerFactory(BaseFactory):
    @classmethod
    def gen_tree_config(
        cls,
        base_top_type: str,
        cls_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        called_from_top: bool,
    ):
        fName = cls_streamer_info["fName"]
        if fName != "TOverrideStreamer":
            return None

        return {
            "factory": cls,
            "name": fName,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        return _cpp.OverrideStreamerReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        int_array, double_array = raw_data

        return awkward.contents.RecordArray(
            [
                awkward.contents.NumpyArray(int_array),
                awkward.contents.NumpyArray(double_array),
            ],
            ["m_int", "m_double"],
        )
