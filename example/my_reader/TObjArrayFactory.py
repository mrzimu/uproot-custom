import awkward.contents
import awkward.index
from uproot_custom import (
    BaseObjectFactory,
    build_cpp_reader,
    gen_tree_config,
    reconstruct_array,
)
from uproot_custom.factories import AnyClassFactory, ObjectHeaderFactory

from . import my_reader_cpp as _cpp


class TObjArrayFactory(BaseObjectFactory):
    @classmethod
    def priority(cls):
        return 50

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ):
        if top_type_name != "TObjArray":
            return None

        item_path = item_path.replace(".TObjArray*", "")
        obj_typename = "TObjInObjArray"

        sub_configs = []
        for s in all_streamer_info[obj_typename]:
            sub_configs.append(
                gen_tree_config(
                    cur_streamer_info=s,
                    all_streamer_info=all_streamer_info,
                    item_path=f"{item_path}.{obj_typename}",
                )
            )

        return {
            "factory": cls,
            "name": cur_streamer_info["fName"],
            "element_config": {
                "factory": ObjectHeaderFactory,
                "name": obj_typename,
                "element_config": {
                    "factory": AnyClassFactory,
                    "name": obj_typename,
                    "sub_configs": sub_configs,
                },
            },
        }

    @classmethod
    def build_cpp_reader(cls, reader_config: dict):
        if reader_config["factory"] != cls:
            return None

        element_config = reader_config["element_config"]
        element_reader = build_cpp_reader(element_config)

        return _cpp.TObjArrayReader(reader_config["name"], element_reader)

    @classmethod
    def reconstruct_array(cls, tree_config: dict, raw_data):
        if tree_config["factory"] != cls:
            return None

        offsets, element_raw_data = raw_data
        element_config = tree_config["element_config"]
        element_data = reconstruct_array(
            element_config,
            element_raw_data,
        )

        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            element_data,
        )
