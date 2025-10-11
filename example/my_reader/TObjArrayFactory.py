import awkward.contents
import awkward.forms
import awkward.index

from uproot_custom import (
    Factory,
    build_factory,
)
from uproot_custom.factories import AnyClassFactory, ObjectHeaderFactory

from . import my_reader_cpp as _cpp


class TObjArrayFactory(Factory):
    @classmethod
    def priority(cls):
        return 50

    @classmethod
    def build_factory(
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

        sub_factories = []
        for s in all_streamer_info[obj_typename]:
            sub_factories.append(
                build_factory(
                    cur_streamer_info=s,
                    all_streamer_info=all_streamer_info,
                    item_path=f"{item_path}.{obj_typename}",
                )
            )

        return cls(
            name=cur_streamer_info["fName"],
            element_factory=ObjectHeaderFactory(
                name=obj_typename,
                element_factory=AnyClassFactory(
                    name=obj_typename,
                    sub_factories=sub_factories,
                ),
            ),
        )

    def __init__(self, name: str, element_factory: Factory):
        super().__init__(name)
        self.element_factory = element_factory

    def build_cpp_reader(self):
        element_reader = self.element_factory.build_cpp_reader()
        return _cpp.TObjArrayReader(self.name, element_reader)

    def make_awkward_content(self, raw_data):
        offsets, element_raw_data = raw_data
        element_data = self.element_factory.make_awkward_content(element_raw_data)
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            element_data,
        )

    def make_awkward_form(self):
        element_form = self.element_factory.make_awkward_form()
        return awkward.forms.ListOffsetForm(
            "i64",
            element_form,
        )
