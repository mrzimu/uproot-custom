import awkward.contents
import awkward.forms

from uproot_custom import Factory

from .my_reader_cpp import OverrideStreamerReader


class OverrideStreamerFactory(Factory):
    @classmethod
    def build_factory(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ):
        fName = cur_streamer_info["fName"]
        if fName != "TOverrideStreamer":
            return None

        return cls(fName)

    def build_cpp_reader(self):
        return OverrideStreamerReader(self.name)

    def make_awkward_content(self, raw_data):
        int_array, double_array = raw_data

        return awkward.contents.RecordArray(
            [
                awkward.contents.NumpyArray(int_array),
                awkward.contents.NumpyArray(double_array),
            ],
            ["m_int", "m_double"],
        )

    def make_awkward_form(self):
        return awkward.forms.RecordForm(
            [
                awkward.forms.NumpyForm("int32"),
                awkward.forms.NumpyForm("float64"),
            ],
            ["m_int", "m_double"],
        )
