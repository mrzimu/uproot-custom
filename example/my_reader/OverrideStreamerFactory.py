import awkward.contents
import awkward.forms

from uproot_custom import BaseFactory

from . import my_reader_cpp as _cpp


class OverrideStreamerFactory(BaseFactory):
    @classmethod
    def gen_tree_config(
        cls,
        base_top_type: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        called_from_top: bool = False,
        **kwargs,
    ):
        fName = cur_streamer_info["fName"]
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

    @classmethod
    def gen_awkward_form(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        return awkward.forms.RecordForm(
            [
                awkward.forms.NumpyForm("int32"),
                awkward.forms.NumpyForm("float64"),
            ],
            ["m_int", "m_double"],
        )
