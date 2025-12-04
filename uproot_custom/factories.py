from __future__ import annotations

from typing import Any, Literal, Union

import awkward as ak
import awkward.contents
import awkward.forms
import awkward.index
import numpy as np
import uproot

import uproot_custom.cpp
from uproot_custom.utils import (
    get_dims_from_branch,
    get_map_key_val_typenames,
    get_sequence_element_typename,
    get_top_type_name,
)

registered_factories: set[type["Factory"]] = set()


def build_factory(
    cur_streamer_info: dict,
    all_streamer_info: dict,
    item_path: str = "",
    **kwargs,
) -> "Factory":
    """
    Generate factory with a given streamer information.

    Args:
        cur_streamer_info (dict): Streamer information of current item.
        all_streamer_info (dict): All streamer information.
        item_path (str): Path to the item.

    Returns:
        An instance of `Factory`.
    """
    fName = cur_streamer_info["fName"]

    top_type_name = (
        get_top_type_name(cur_streamer_info["fTypeName"])
        if "fTypeName" in cur_streamer_info
        else None
    )

    if not kwargs.get("called_from_top", False):
        item_path = f"{item_path}.{fName}"

    for factory_class in sorted(
        registered_factories, key=lambda x: x.priority(), reverse=True
    ):
        factory_instance = factory_class.build_factory(
            top_type_name,
            cur_streamer_info,
            all_streamer_info,
            item_path,
            **kwargs,
        )
        if factory_instance is not None:
            return factory_instance

    raise ValueError(f"Unknown type: {cur_streamer_info['fTypeName']} for {item_path}")


def read_branch(
    branch: uproot.TBranch,
    data: np.ndarray[np.uint8],
    offsets: np.ndarray,
    cur_streamer_info: dict,
    all_streamer_info: dict[str, list[dict]],
    item_path: str = "",
):
    factory = build_factory(
        cur_streamer_info,
        all_streamer_info,
        item_path,
        called_from_top=True,
        branch=branch,
    )
    reader = factory.build_cpp_reader()

    if offsets is None:
        nbyte = cur_streamer_info["fSize"]
        offsets = np.arange(data.size // nbyte + 1, dtype=np.uint32) * nbyte
    raw_data = uproot_custom.cpp.read_data(data, offsets, reader)

    return factory.make_awkward_content(raw_data)


def read_branch_awkward_form(
    branch: uproot.TBranch,
    cur_streamer_info: dict,
    all_streamer_info: dict[str, list[dict]],
    item_path: str = "",
):
    factory = build_factory(
        cur_streamer_info,
        all_streamer_info,
        item_path,
        called_from_top=True,
        branch=branch,
    )
    return factory.make_awkward_form()


class Factory:
    """
    Base class of reader factories. Reader factory is in charge of
    generating reader configuration tree, build an combine C++ reader
    and reconstruct raw array from C++ reader into structured awkward
    array.
    """

    @classmethod
    def priority(cls) -> int:
        """
        Return the call priority of this factory. Factories with higher
        priority will be called first.
        """
        return 10

    @classmethod
    def build_factory(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ) -> Union[None, Factory]:
        """
        Return an instance of this factory when current item matches this factory,
        otherwise return `None`.

        Args:
            top_type_name (str): Name of the top-level class of current item.
                For example, `vector<int>` -> `vector`.
            cur_streamer_info (dict): Streamer information of current item.
            all_streamer_info (dict): Dictionary storing streamer information
                of all types. The key is the classname, pair is a dictionary
                like `cur_streamer_info`.
            item_path (str): Indicating which item is being matched. One can
                use this variable to apply specific behavior.

        Returns:
            A dictionary containing all necessary information of building
            C++ reader and reconstruct raw data to awkward array for current
            item.
        """
        return None

    def __init__(self, name: str):
        self.name = name

    def build_cpp_reader(self) -> uproot_custom.cpp.IReader:
        """
        Build concrete C++ reader.

        Returns:
            An instance of `uproot_custom.cpp.IReader`.
        """
        raise NotImplementedError("build_cpp_reader not implemented.")

    def make_awkward_content(
        self,
        raw_data: Any,
    ) -> awkward.contents.Content:
        """
        Reconstruct awkward contents with raw data returned from the C++ reader.

        Args:
            raw_data: Data returned from C++ reader.

        Returns:
            awkward.contents.Content: Awkward content to build corresponding array.
        """
        raise NotImplementedError("reconstruct_array not implemented.")

    def make_awkward_form(self) -> awkward.forms.Form:
        """
        Generate awkward form with tree configuration.

        Returns:
            awkward.forms.Form: Awkward form of current item.
        """
        raise NotImplementedError("gen_awkward_form not implemented.")


class PrimitiveFactory(Factory):
    typenames = {
        "bool": "bool",
        "char": "i1",
        "short": "i2",
        "int": "i4",
        "long": "i8",
        "long long": "i8",
        "signed char": "i1",
        "signed short": "i2",
        "signed int": "i4",
        "signed long": "i8",
        "signed long long": "i8",
        "unsigned char": "u1",
        "unsigned short": "u2",
        "unsigned int": "u4",
        "unsigned long": "u8",
        "unsigned long long": "u8",
        "float": "f",
        "double": "d",
        # cstdint
        "int8_t": "i1",
        "int16_t": "i2",
        "int32_t": "i4",
        "int64_t": "i8",
        "uint8_t": "u1",
        "uint16_t": "u2",
        "uint32_t": "u4",
        "uint64_t": "u8",
        # ROOT types
        "Bool_t": "bool",
        "Char_t": "i1",
        "Short_t": "i2",
        "Int_t": "i4",
        "Long_t": "i8",
        "UChar_t": "u1",
        "UShort_t": "u2",
        "UInt_t": "u4",
        "ULong_t": "u8",
        "Float_t": "f",
        "Double_t": "d",
    }

    ftypes = {
        1: "i1",
        2: "i2",
        3: "i4",
        4: "i8",
        5: "f",
        8: "d",
        11: "u1",
        12: "u2",
        13: "u4",
        14: "u8",
        18: "bool",
    }

    cpp_reader_map = {
        "bool": uproot_custom.cpp.BoolReader,
        "i1": uproot_custom.cpp.Int8Reader,
        "i2": uproot_custom.cpp.Int16Reader,
        "i4": uproot_custom.cpp.Int32Reader,
        "i8": uproot_custom.cpp.Int64Reader,
        "u1": uproot_custom.cpp.UInt8Reader,
        "u2": uproot_custom.cpp.UInt16Reader,
        "u4": uproot_custom.cpp.UInt32Reader,
        "u8": uproot_custom.cpp.UInt64Reader,
        "f": uproot_custom.cpp.FloatReader,
        "d": uproot_custom.cpp.DoubleReader,
    }

    ctype_primitive_map = {
        "bool": "bool",
        "i1": "int8",
        "i2": "int16",
        "i4": "int32",
        "i8": "int64",
        "u1": "uint8",
        "u2": "uint16",
        "u4": "uint32",
        "u8": "uint64",
        "f": "float32",
        "d": "float64",
    }

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is primitive type.
        """
        ctype = cls.ftypes.get(cur_streamer_info.get("fType", -1), None)
        if ctype is None:
            ctype = cls.typenames.get(top_type_name, None)

        if ctype is None:
            return None

        return cls(name=cur_streamer_info["fName"], ctype=ctype)

    def __init__(self, name: str, ctype: str):
        self.name = name
        self.ctype = ctype

    def build_cpp_reader(self):
        return self.cpp_reader_map[self.ctype](self.name)

    def make_awkward_content(self, raw_data: np.ndarray):
        if self.ctype == "bool":
            raw_data = raw_data.astype(np.bool_)
        return ak.contents.NumpyArray(raw_data)

    def make_awkward_form(self):
        return ak.forms.NumpyForm(self.ctype_primitive_map[self.ctype])


stl_typenames = {
    "vector",
    "array",
    "string",
    "list",
    "set",
    "multiset",
    "unordered_set",
    "unordered_multiset",
    "map",
    "multimap",
    "unordered_map",
    "unordered_multimap",
}


class STLSeqFactory(Factory):
    """
    This factory reads sequence-like STL containers.
    """

    target_types = [
        "vector",
        "array",
        "list",
        "set",
        "multiset",
        "unordered_set",
        "unordered_multiset",
    ]

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is in `cls.target_types`.
        """
        if top_type_name not in cls.target_types:
            return None

        fName = cur_streamer_info["fName"]
        fTypeName = cur_streamer_info["fTypeName"]
        element_type = get_sequence_element_typename(fTypeName)
        element_info = {
            "fName": fName,
            "fTypeName": element_type,
        }

        element_factory = build_factory(
            element_info,
            all_streamer_info,
            item_path,
        )

        if isinstance(element_factory, (STLSeqFactory, STLMapFactory, STLStringFactory)):
            element_factory.with_header = False

        return cls(
            name=fName,
            with_header=True,
            objwise_or_memberwise=-1,
            element_factory=element_factory,
        )

    def __init__(
        self,
        name: str,
        with_header: bool,
        objwise_or_memberwise: Literal[-1, 0, 1],
        element_factory: Factory,
    ):
        self.name = name
        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.element_factory = element_factory

    def build_cpp_reader(self):
        element_cpp_reader = self.element_factory.build_cpp_reader()

        return uproot_custom.cpp.STLSeqReader(
            self.name,
            self.with_header,
            self.objwise_or_memberwise,
            element_cpp_reader,
        )

    def make_awkward_content(self, raw_data):
        offsets, element_raw_data = raw_data
        element_content = self.element_factory.make_awkward_content(element_raw_data)
        return ak.contents.ListOffsetArray(
            ak.index.Index64(offsets),
            element_content,
        )

    def make_awkward_form(self):
        element_form = self.element_factory.make_awkward_form()
        return ak.forms.ListOffsetForm(
            "i64",
            element_form,
        )


class STLMapFactory(Factory):
    """
    This class reads mapping-like STL containers.
    """

    target_types = ["map", "unordered_map", "multimap", "unordered_multimap"]

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is in `cls.target_types`.
        """
        if top_type_name not in cls.target_types:
            return None

        fTypeName = cur_streamer_info["fTypeName"]
        key_type_name, val_type_name = get_map_key_val_typenames(fTypeName)

        fName = cur_streamer_info["fName"]
        key_info = {
            "fName": "key",
            "fTypeName": key_type_name,
        }

        val_info = {
            "fName": "val",
            "fTypeName": val_type_name,
        }

        key_factory = build_factory(key_info, all_streamer_info, item_path)
        val_factory = build_factory(val_info, all_streamer_info, item_path)

        return cls(
            name=fName,
            with_header=True,
            objwise_or_memberwise=-1,
            key_factory=key_factory,
            val_factory=val_factory,
        )

    def __init__(
        self,
        name: str,
        with_header: bool,
        objwise_or_memberwise: Literal[-1, 0, 1],
        key_factory: Factory,
        val_factory: Factory,
    ):
        self.name = name
        self.with_header = with_header
        self.objwise_or_memberwise = objwise_or_memberwise
        self.key_factory = key_factory
        self.val_factory = val_factory

    def build_cpp_reader(self):
        is_obj_wise = self.objwise_or_memberwise == 0

        if is_obj_wise:
            self.key_factory.with_header = False
            self.val_factory.with_header = False

        key_cpp_reader = self.key_factory.build_cpp_reader()
        val_cpp_reader = self.val_factory.build_cpp_reader()

        return uproot_custom.cpp.STLMapReader(
            self.name,
            self.with_header,
            self.objwise_or_memberwise,
            key_cpp_reader,
            val_cpp_reader,
        )

    def make_awkward_content(self, raw_data):
        offsets, key_raw_data, val_raw_data = raw_data
        key_content = self.key_factory.make_awkward_content(key_raw_data)
        val_content = self.val_factory.make_awkward_content(val_raw_data)

        return ak.contents.ListOffsetArray(
            ak.index.Index64(offsets),
            ak.contents.RecordArray(
                [key_content, val_content],
                [self.key_factory.name, self.val_factory.name],
            ),
        )

    def make_awkward_form(self):
        key_form = self.key_factory.make_awkward_form()
        val_form = self.val_factory.make_awkward_form()
        return ak.forms.ListOffsetForm(
            "i64",
            ak.forms.RecordForm(
                [key_form, val_form],
                [self.key_factory.name, self.val_factory.name],
            ),
        )


class STLStringFactory(Factory):
    """
    This class reads std::string.
    """

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        if top_type_name != "string":
            return None

        return cls(
            name=cur_streamer_info["fName"],
            with_header=True,
        )

    def __init__(self, name: str, with_header: bool):
        self.name = name
        self.with_header = with_header

    def build_cpp_reader(self):
        return uproot_custom.cpp.STLStringReader(
            self.name,
            self.with_header,
        )

    def make_awkward_content(self, raw_data):
        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data, parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )

    def make_awkward_form(self):
        return ak.forms.ListOffsetForm(
            "i64",
            ak.forms.NumpyForm("uint8", parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )


class TArrayFactory(Factory):
    """
    This class reads TArray from a binary paerser.

    TArray includes TArrayC, TArrayS, TArrayI, TArrayL, TArrayL64, TArrayF, and TArrayD.
    Corresponding ctype is u1, u2, i4, i8, i8, f, and d.
    """

    typenames = {
        "TArrayC": "i1",
        "TArrayS": "i2",
        "TArrayI": "i4",
        "TArrayL": "i8",
        "TArrayL64": "i8",
        "TArrayF": "f",
        "TArrayD": "d",
    }

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is in `cls.typenames`.
        """
        if top_type_name not in cls.typenames:
            return None

        ctype = cls.typenames[top_type_name]
        return cls(name=cur_streamer_info["fName"], ctype=ctype)

    def __init__(self, name: str, ctype: str):
        super().__init__(name)
        self.ctype = ctype

    def build_cpp_reader(self):
        return {
            "i1": uproot_custom.cpp.TArrayCReader,
            "i2": uproot_custom.cpp.TArraySReader,
            "i4": uproot_custom.cpp.TArrayIReader,
            "i8": uproot_custom.cpp.TArrayLReader,
            "f": uproot_custom.cpp.TArrayFReader,
            "d": uproot_custom.cpp.TArrayDReader,
        }[self.ctype](self.name)

    def make_awkward_content(self, raw_data):
        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data),
        )

    def make_awkward_form(self):
        return ak.forms.ListOffsetForm(
            "i64",
            ak.forms.NumpyForm(PrimitiveFactory.ctype_primitive_map[self.ctype]),
        )


class TStringFactory(Factory):
    """
    This class reads TString from a binary parser.
    """

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        if top_type_name != "TString":
            return None

        return cls(
            name=cur_streamer_info["fName"],
            with_header=False,
        )

    def __init__(self, name: str, with_header: bool):
        super().__init__(name)
        self.with_header = with_header

    def build_cpp_reader(self):
        return uproot_custom.cpp.TStringReader(self.name, self.with_header)

    def make_awkward_content(self, raw_data):
        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data, parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )

    def make_awkward_form(self):
        return ak.forms.ListOffsetForm(
            "i64",
            ak.forms.NumpyForm("uint8", parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )


class TObjectFactory(Factory):
    """
    This class reads base TObject from a binary parser.
    You should skip reconstructing array when this factory
    keeps no data, since the method `reconstruct_array`
    will always return `None`.
    """

    # Whether keep TObject data.
    keep_data_itempaths: set[str] = set()

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        The configuration contains:
        - `factory`: cls
        - `name: fName,
        - `keep_data`: Whether keep data from TObject.
        """
        if top_type_name != "BASE":
            return None

        fType = cur_streamer_info["fType"]
        if fType != 66:
            return None

        return cls(
            name=cur_streamer_info["fName"],
            keep_data=item_path in cls.keep_data_itempaths,
        )

    def __init__(self, name: str, keep_data: bool):
        super().__init__(name)
        self.keep_data = keep_data

    def build_cpp_reader(self):
        return uproot_custom.cpp.TObjectReader(
            self.name,
            self.keep_data,
        )

    def make_awkward_content(self, raw_data):
        if not self.keep_data:
            return awkward.contents.EmptyArray()

        unique_ids, bits, pidf, pidf_offsets = raw_data
        return awkward.contents.RecordArray(
            [
                awkward.contents.NumpyArray(unique_ids),
                awkward.contents.NumpyArray(bits),
                awkward.contents.ListOffsetArray(
                    awkward.index.Index64(pidf_offsets),
                    awkward.contents.NumpyArray(pidf),
                ),
            ],
            ["fUniqueID", "fBits", "pidf"],
        )

    def make_awkward_form(self):
        if not self.keep_data:
            return ak.forms.EmptyForm()

        return ak.forms.RecordForm(
            [
                ak.forms.NumpyForm("int32"),  # fUniqueID
                ak.forms.NumpyForm("uint32"),  # fBits
                ak.forms.ListOffsetForm(
                    "i64",
                    ak.forms.NumpyForm("uint16"),  # pidf
                ),
            ],
            ["fUniqueID", "fBits", "pidf"],
        )


class CStyleArrayFactory(Factory):
    """
    This class reads a C-style array from a binary parser.
    """

    @classmethod
    def priority(cls):
        return 20  # This reader should be called first

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        fTypeName = cur_streamer_info.get("fTypeName", "")
        dims = ()
        if kwargs.get("called_from_top", False):
            branch = kwargs["branch"]
            dims, is_jagged = get_dims_from_branch(branch)
            if is_jagged and not fTypeName.endswith("[]"):
                fTypeName += "[]"

        if not fTypeName.endswith("[]") and cur_streamer_info.get("fArrayDim", 0) == 0:
            return None

        fName = cur_streamer_info["fName"]
        fArrayDim = cur_streamer_info.get("fArrayDim", None)
        fMaxIndex = cur_streamer_info.get("fMaxIndex", None)

        if fTypeName.endswith("[]"):
            flat_size = -1
        else:
            assert fArrayDim is not None, f"fArrayDim cannot be None for {item_path}."
            assert fMaxIndex is not None, f"fMaxIndex cannot be None for {item_path}."
            flat_size = np.prod(fMaxIndex[:fArrayDim])

        element_streamer_info = cur_streamer_info.copy()
        element_streamer_info["fArrayDim"] = 0
        while fTypeName.endswith("[]"):
            fTypeName = fTypeName[:-2]
        element_streamer_info["fTypeName"] = fTypeName

        element_factory = build_factory(
            element_streamer_info,
            all_streamer_info,
            item_path=item_path,
        )

        # When TString is stored in C-style or std array, it has a "fNByte+fVersion" header.
        if isinstance(element_factory, TStringFactory) and fArrayDim != 0:
            element_factory.with_header = True

        assert flat_size != 0, f"flatten_size cannot be 0."

        # When stored in std::array
        # [1] There is no header for vector and map.
        # [2] Map is object-wise serialized.
        # By so far, we use fType==82 to identify std::array.
        if (
            isinstance(
                element_factory,
                (
                    STLSeqFactory,
                    STLMapFactory,
                    STLStringFactory,
                ),
            )
            and cur_streamer_info.get("fType", -1) == 82
        ):
            element_factory.with_header = False
            element_factory.objwise_or_memberwise = 0  # -1: auto, 0: obj-wise, 1: member-wise

        return cls(
            name=fName,
            element_factory=element_factory,
            flat_size=flat_size,
            fMaxIndex=fMaxIndex,
            fArrayDim=fArrayDim,
        )

    def __init__(
        self,
        name: str,
        element_factory: Factory,
        flat_size: int,
        fMaxIndex: int,
        fArrayDim: np.ndarray,
    ):
        super().__init__(name)
        self.element_factory = element_factory
        self.flat_size = flat_size
        self.fMaxIndex = fMaxIndex
        self.fArrayDim = fArrayDim

    def build_cpp_reader(self):
        element_reader = self.element_factory.build_cpp_reader()
        return uproot_custom.cpp.CStyleArrayReader(
            self.name,
            self.flat_size,
            element_reader,
        )

    def make_awkward_content(self, raw_data):
        if self.flat_size < 0:
            element_raw_data = raw_data[1]
        else:
            element_raw_data = raw_data

        element_content = self.element_factory.make_awkward_content(element_raw_data)

        if self.fArrayDim is not None and self.fMaxIndex is not None:
            shape = [self.fMaxIndex[i] for i in range(self.fArrayDim)]
            for s in shape[::-1]:
                element_content = awkward.contents.RegularArray(element_content, int(s))
        else:
            shape = ()

        if self.flat_size < 0:
            offsets = raw_data[0]
            for s in shape:
                offsets = offsets / s

            return ak.contents.ListOffsetArray(
                ak.index.Index64(offsets),
                element_content,
            )
        else:
            return element_content

    def make_awkward_form(self):
        element_form = self.element_factory.make_awkward_form()
        if self.fArrayDim is not None and self.fMaxIndex is not None:
            shape = [self.fMaxIndex[i] for i in range(self.fArrayDim)]
            for s in shape[::-1]:
                element_form = ak.forms.RegularForm(element_form, int(s))

        if self.flat_size < 0:
            return ak.forms.ListOffsetForm(
                "i64",
                element_form,
            )
        else:
            return element_form


class GroupFactory(Factory):
    """
    This factory groups differernt factory together. You can use
    this factory to read specific format of data as you like.
    """

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Never match items. If one needs to use this factory,
        instatiate it directly.
        """
        return None

    def __init__(self, name: str, sub_factories: list[Factory]):
        super().__init__(name)
        self.sub_factories = sub_factories

    def build_cpp_reader(self):
        sub_readers = [s.build_cpp_reader() for s in self.sub_factories]
        return uproot_custom.cpp.GroupReader(self.name, sub_readers)

    def make_awkward_content(self, raw_data):
        sub_configs = self.sub_factories

        sub_fields = []
        sub_contents = []
        for s_fac, s_data in zip(sub_configs, raw_data):
            s_cont = s_fac.make_awkward_content(s_data)
            if isinstance(s_cont, awkward.contents.EmptyArray):
                continue

            sub_fields.append(s_fac.name)
            sub_contents.append(s_cont)

        if len(sub_contents) == 0:
            return awkward.contents.EmptyArray()
        else:
            return awkward.contents.RecordArray(sub_contents, sub_fields)

    def make_awkward_form(self):
        sub_configs = self.sub_factories

        sub_fields = []
        sub_contents = []
        for s_fac in sub_configs:
            s_form = s_fac.make_awkward_form()
            if isinstance(s_form, ak.forms.EmptyForm):
                continue

            sub_fields.append(s_fac.name)
            sub_contents.append(s_form)

        if len(sub_contents) == 0:
            return ak.forms.EmptyForm()
        else:
            return ak.forms.RecordForm(sub_contents, sub_fields)


class BaseObjectFactory(GroupFactory):
    """
    This class reads base-object of an object. The base object has
    fNBytes(uint32), fVersion(uint16) at the beginning.
    """

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        if top_type_name != "BASE":
            return None

        fType = cls_streamer_info["fType"]
        if fType != 0:
            return None

        fName = cls_streamer_info["fName"]
        sub_streamers: list[dict] = all_streamer_info[fName]
        sub_factories = [build_factory(s, all_streamer_info, item_path) for s in sub_streamers]

        return cls(name=fName, sub_factories=sub_factories)

    def build_cpp_reader(self):
        sub_readers = [s.build_cpp_reader() for s in self.sub_factories]
        return uproot_custom.cpp.GroupReader(self.name, sub_readers)


class AnyClassFactory(GroupFactory):
    """
    This class tries to read any class object that is not handled by other factories.
    """

    @classmethod
    def priority(cls):
        return 0  # This reader should be called last

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        sub_streamers: list = all_streamer_info[top_type_name]
        sub_factories = [build_factory(s, all_streamer_info, item_path) for s in sub_streamers]
        return cls(name=top_type_name, sub_factories=sub_factories)

    def build_cpp_reader(self):
        sub_readers = [s.build_cpp_reader() for s in self.sub_factories]
        return uproot_custom.cpp.AnyClassReader(self.name, sub_readers)


class ObjectHeaderFactory(Factory):
    """
    This class reads object header:
    1. fNBytes
    2. fTag
    3. if (fTag == -1) null-terminated-string

    If will be called automatically if no other factory matches.
    Also, it can be manually used to read object header.
    """

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        This factory will always match items. If one needs to use this factory,
        instatiate it directly.
        """
        return None

    def __init__(self, name: str, element_factory: Factory):
        super().__init__(name)
        self.element_factory = element_factory

    def build_cpp_reader(self):
        element_reader = self.element_factory.build_cpp_reader()
        return uproot_custom.cpp.ObjectHeaderReader(self.name, element_reader)

    def make_awkward_content(self, raw_data):
        return self.element_factory.make_awkward_content(raw_data)

    def make_awkward_form(self):
        return self.element_factory.make_awkward_form()


class EmptyFactory(Factory):
    """
    This factory does nothing. It's just a place holder.
    """

    @classmethod
    def build_factory(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        This factory will never match items. If one needs to use this factory,
        instatiate it directly.
        """
        return None

    def build_cpp_reader(self):
        return uproot_custom.cpp.EmptyReader(self.name)

    def make_awkward_content(self, raw_data):
        return awkward.contents.EmptyArray()

    def make_awkward_form(self):
        return ak.forms.EmptyForm()


registered_factories |= {
    PrimitiveFactory,
    STLSeqFactory,
    STLMapFactory,
    STLStringFactory,
    TArrayFactory,
    TStringFactory,
    TObjectFactory,
    CStyleArrayFactory,
    GroupFactory,
    BaseObjectFactory,
    AnyClassFactory,
    ObjectHeaderFactory,
    EmptyFactory,
}
