from __future__ import annotations

from typing import Any, Union

import awkward as ak
import awkward.contents
import awkward.index
import numpy as np

import uproot_custom.cpp
from uproot_custom.utils import (
    get_map_key_val_typenames,
    get_sequence_element_typename,
    get_top_type_name,
)

registered_factories: set[type["BaseFactory"]] = set()


def gen_tree_config(
    cur_streamer_info: dict,
    all_streamer_info: dict,
    item_path: str = "",
    **kwargs,
) -> dict:
    """
    Generate reader configuration with a given streamer information.

    Args:
        cur_streamer_info (dict): Streamer information of current item.
        all_streamer_info (dict): All streamer information.
        item_path (str): Path to the item.

    Returns:
        dict: Reader configuration.
    """
    fName = cur_streamer_info["fName"]

    top_type_name = (
        get_top_type_name(cur_streamer_info["fTypeName"])
        if "fTypeName" in cur_streamer_info
        else None
    )

    if not kwargs.get("called_from_top", False):
        item_path = f"{item_path}.{fName}"

    for reader in sorted(registered_factories, key=lambda x: x.priority(), reverse=True):
        tree_config = reader.gen_tree_config(
            top_type_name,
            cur_streamer_info,
            all_streamer_info,
            item_path,
            **kwargs,
        )
        if tree_config is not None:
            return tree_config

    raise ValueError(f"Unknown type: {cur_streamer_info['fTypeName']} for {item_path}")


def build_cpp_reader(tree_config: dict):
    for reader in sorted(registered_factories, key=lambda x: x.priority(), reverse=True):
        cpp_reader = reader.build_cpp_reader(tree_config)
        if cpp_reader is not None:
            return cpp_reader

    raise ValueError(
        f"Unknown factory type: {tree_config['factory']} for {tree_config['name']}"
    )


def reconstruct_array(
    tree_config: dict,
    raw_data: Union[np.ndarray, tuple, list, None],
) -> Union[ak.Array, None]:
    for reader in sorted(registered_factories, key=lambda x: x.priority(), reverse=True):
        data = reader.reconstruct_array(tree_config, raw_data)
        if data is not None:
            return data

    raise ValueError(
        f"Unknown factory type: {tree_config['factory']} for {tree_config['name']}"
    )


def read_branch(
    data: np.ndarray[np.uint8],
    offsets: np.ndarray,
    cur_streamer_info: dict,
    all_streamer_info: dict[str, list[dict]],
    item_path: str = "",
):
    tree_config = gen_tree_config(
        cur_streamer_info,
        all_streamer_info,
        item_path,
        called_from_top=True,
    )
    reader = build_cpp_reader(tree_config)

    if offsets is None:
        nbyte = cur_streamer_info["fSize"]
        offsets = np.arange(data.size // nbyte + 1, dtype=np.uint32) * nbyte
    raw_data = uproot_custom.cpp.read_data(data, offsets, reader)

    return reconstruct_array(tree_config, raw_data)


class BaseFactory:
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
    def gen_tree_config(
        cls,
        top_type_name: str,
        cur_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str,
        **kwargs,
    ) -> Union[None, dict]:
        """
        Return tree configuration when current item matches this factory,
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

    @classmethod
    def build_cpp_reader(
        cls,
        tree_config: dict,
    ) -> Union[None, uproot_custom.cpp.IElementReader]:
        """
        Read `tree_config`, build concrete C++ reader when current item matches
        this factory, otherwise return `None`.

        Args:
            tree_config (dict): Tree configuration of current item.

        Returns:
            When current item matches this factory, return corresponding C++ reader,
            otherwise return `None`.
        """
        return None

    @classmethod
    def reconstruct_array(
        cls,
        tree_config: dict,
        raw_data: Any,
    ) -> Union[awkward.contents.Content]:
        """
        Reconstruct awkward contents with raw data returned from the C++ reader.

        Args:
            tree_config (dict): Tree configuration of current item.
            raw_data: Data returned from C++ reader.

        Returns:
            awkward.contents.Content: Awkward content to build corresponding array.
        """
        return None


class BasicTypeFactory(BaseFactory):
    typenames = {
        "bool": "bool",
        "char": "i1",
        "short": "i2",
        "int": "i4",
        "long": "i8",
        "long long": "i8",
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

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is basic type.
        The configuration contains:

        - `factory`: cls
        - `name`: fName
        - `ctype`: Concrete basic type (`bool`, `[i,u]`x`[1,2,4,8]`, `f`, `d`)
        """
        if top_type_name in cls.typenames:
            ctype = cls.typenames[top_type_name]
            return {
                "factory": cls,
                "name": cur_streamer_info["fName"],
                "ctype": ctype,
            }
        else:
            return None

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        ctype = tree_config["ctype"]
        return cls.cpp_reader_map[ctype](tree_config["name"])

    @classmethod
    def reconstruct_array(
        cls,
        tree_config: dict,
        raw_data: np.ndarray,
    ):
        if tree_config["factory"] is not cls:
            return None

        if tree_config["ctype"] == "bool":
            raw_data = raw_data.astype(np.bool_)
        return ak.contents.NumpyArray(raw_data)


stl_typenames = {
    "vector",
    "array",
    "map",
    "unordered_map",
    "string",
    "list",
    "set",
    "unordered_set",
}


class STLSeqFactory(BaseFactory):
    """
    This factory reads sequence-like STL containers.
    """

    target_types = [
        "vector",
        "array",
        "list",
        "set",
        "unordered_set",
    ]

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is in `cls.target_types`.
        The returned configuration contains:

        - `factory`: cls
        - `name`: fName
        - `element_config`: Configuration of current container's element reader.
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

        elemeng_config = gen_tree_config(
            element_info,
            all_streamer_info,
            item_path,
        )

        top_element_type = get_top_type_name(element_type)
        if top_element_type in stl_typenames:
            elemeng_config["with_header"] = False

        return {
            "factory": cls,
            "name": fName,
            "element_config": elemeng_config,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        element_cpp_reader = build_cpp_reader(tree_config["element_config"])
        with_header = tree_config.get("with_header", True)
        return uproot_custom.cpp.STLSeqReader(
            tree_config["name"],
            with_header,
            element_cpp_reader,
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        offsets, element_raw_data = raw_data
        element_data = reconstruct_array(
            tree_config["element_config"],
            element_raw_data,
        )

        return ak.contents.ListOffsetArray(
            ak.index.Index64(offsets),
            element_data,
        )


class STLMapFactory(BaseFactory):
    """
    This class reads mapping-like STL containers.
    """

    target_types = ["map", "unordered_map", "multimap"]

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Return when `top_type_name` is in `cls.target_types`.
        The returned configuration contains:

        - `factory`: cls
        - `name`: fName
        - `key_config`: Configuration of current container's key reader.
        - `val_config`: Configuration of current container's value reader.
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

        key_config = gen_tree_config(key_info, all_streamer_info, item_path)
        if get_top_type_name(key_type_name) in stl_typenames:
            key_config["with_header"] = False

        val_config = gen_tree_config(val_info, all_streamer_info, item_path)
        if get_top_type_name(val_type_name) in stl_typenames:
            val_config["with_header"] = False

        return {
            "factory": cls,
            "name": fName,
            "key_config": key_config,
            "val_config": val_config,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        key_cpp_reader = build_cpp_reader(tree_config["key_config"])
        val_cpp_reader = build_cpp_reader(tree_config["val_config"])
        with_header = tree_config.get("with_header", True)
        return uproot_custom.cpp.STLMapReader(
            tree_config["name"],
            with_header,
            key_cpp_reader,
            val_cpp_reader,
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        key_config = tree_config["key_config"]
        val_config = tree_config["val_config"]
        offsets, key_raw_data, val_raw_data = raw_data
        key_data = reconstruct_array(key_config, key_raw_data)
        val_data = reconstruct_array(val_config, val_raw_data)

        return ak.contents.ListOffsetArray(
            ak.index.Index64(offsets),
            ak.contents.RecordArray(
                [key_data, val_data],
                [key_config["name"], val_config["name"]],
            ),
        )


class STLStringFactory(BaseFactory):
    """
    This class reads std::string.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        if top_type_name != "string":
            return None

        called_from_top = kwargs.get("called_from_top", False)
        return {
            "factory": cls,
            "name": cur_streamer_info["fName"],
            "with_header": not called_from_top,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        return uproot_custom.cpp.STLStringReader(
            tree_config["name"],
            tree_config.get("with_header", True),
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data, parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )


class TArrayFactory(BaseFactory):
    """
    This class reads TArray from a binary paerser.

    TArray includes TArrayC, TArrayS, TArrayI, TArrayL, TArrayF, and TArrayD.
    Corresponding ctype is u1, u2, i4, i8, f, and d.
    """

    typenames = {
        "TArrayC": "i1",
        "TArrayS": "i2",
        "TArrayI": "i4",
        "TArrayL": "i8",
        "TArrayF": "f",
        "TArrayD": "d",
    }

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        The configuration contains:
        - reader: cls
        - name: fName
        - ctype: Concrete basic type (`i1`, `i2`, `i4`, `i8`, `f`, `d`)
        """
        if top_type_name not in cls.typenames:
            return None

        ctype = cls.typenames[top_type_name]
        return {
            "factory": cls,
            "name": cur_streamer_info["fName"],
            "ctype": ctype,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        ctype = tree_config["ctype"]

        return {
            "i1": uproot_custom.cpp.TArrayCReader,
            "i2": uproot_custom.cpp.TArraySReader,
            "i4": uproot_custom.cpp.TArrayIReader,
            "i8": uproot_custom.cpp.TArrayLReader,
            "f": uproot_custom.cpp.TArrayFReader,
            "d": uproot_custom.cpp.TArrayDReader,
        }[ctype](tree_config["name"])

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data),
        )


class TStringFactory(BaseFactory):
    """
    This class reads TString from a binary parser.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        if top_type_name != "TString":
            return None

        return {
            "factory": cls,
            "name": cur_streamer_info["fName"],
        }

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        return uproot_custom.cpp.TStringReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data, parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )


class TObjectFactory(BaseFactory):
    """
    This class reads base TObject from a binary parser.
    You should skip reconstructing array when this factory
    keeps no data, since the method `reconstruct_array`
    will always return `None`.
    """

    # Whether keep TObject data.
    keep_data_itempaths: set[str] = set()

    @classmethod
    def gen_tree_config(
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

        return {
            "factory": cls,
            "name": cur_streamer_info["fName"],
            "keep_data": item_path in cls.keep_data_itempaths,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        if tree_config["factory"] is not cls:
            return None

        return uproot_custom.cpp.TObjectReader(
            tree_config["name"],
            tree_config["keep_data"],
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        if not tree_config["keep_data"]:
            return None

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


class CStyleArrayFactory(BaseFactory):
    """
    This class reads a C-style array from a binary parser.
    """

    @classmethod
    def priority(cls):
        return 20  # This reader should be called first

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        fTypeName = cur_streamer_info.get("fTypeName", "")
        if not fTypeName.endswith("[]") and cur_streamer_info.get("fArrayDim", 0) == 0:
            return None

        fName = cur_streamer_info["fName"]

        if fTypeName.endswith("[]"):
            fArrayDim = -1
            fMaxIndex = -1
            flat_size = -1
        else:
            fArrayDim = cur_streamer_info["fArrayDim"]
            fMaxIndex = cur_streamer_info["fMaxIndex"]
            flat_size = np.prod(fMaxIndex[:fArrayDim])

        element_streamer_info = cur_streamer_info.copy()
        element_streamer_info["fArrayDim"] = 0
        while fTypeName.endswith("[]"):
            fTypeName = fTypeName[:-2]
        element_streamer_info["fTypeName"] = fTypeName

        element_config = gen_tree_config(
            element_streamer_info,
            all_streamer_info,
        )

        assert flat_size != 0, f"flatten_size cannot be 0."

        # c-type number or TArray
        top_type_name = get_top_type_name(fTypeName)
        if top_type_name in BasicTypeFactory.typenames or fTypeName in TArrayFactory.typenames:
            return {
                "factory": cls,
                "name": fName,
                "is_obj": False,
                "element_config": element_config,
                "flat_size": flat_size,
                "fMaxIndex": fMaxIndex,
                "fArrayDim": fArrayDim,
            }

        # TSTring
        elif top_type_name == "TString":
            return {
                "factory": cls,
                "name": fName,
                "is_obj": True,
                "element_config": element_config,
                "flat_size": flat_size,
                "fMaxIndex": fMaxIndex,
                "fArrayDim": fArrayDim,
            }

        # STL
        elif top_type_name in stl_typenames:
            element_config["with_header"] = False

            is_obj = not kwargs.get("called_from_top", False)
            if cur_streamer_info.get("fType", 0) == 500:
                is_obj = True

            # when is a ragged array, vector/map will have a factory
            element_factory = element_config.get("factory", None)
            if (
                flat_size < 0
                and element_factory is not None
                and element_factory is not BasicTypeFactory
            ):
                is_obj = True

            is_stl_mapping = top_type_name in STLMapFactory.target_types

            return {
                "factory": cls,
                "name": fName,
                "is_obj": is_obj,
                "is_stl_mapping": is_stl_mapping,
                "flat_size": flat_size,
                "element_config": element_config,
                "fMaxIndex": fMaxIndex,
                "fArrayDim": fArrayDim,
            }

        else:
            raise ValueError(f"Unknown type: {top_type_name} for C-style array: {fTypeName}")

    @classmethod
    def build_cpp_reader(cls, tree_config: dict):
        reader_type = tree_config["factory"]
        if reader_type is not cls:
            return None

        element_reader = build_cpp_reader(tree_config["element_config"])

        return uproot_custom.cpp.CArrayReader(
            tree_config["name"],
            tree_config["is_obj"],
            tree_config.get("is_stl_mapping", False),
            tree_config["flat_size"],
            element_reader,
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        element_config = tree_config["element_config"]
        flat_size = tree_config["flat_size"]

        if flat_size > 0:
            fMaxIndex = tree_config["fMaxIndex"]
            fArrayDim = tree_config["fArrayDim"]
            shape = [fMaxIndex[i] for i in range(fArrayDim)]

            element_data = reconstruct_array(
                element_config,
                raw_data,
            )

            for s in shape[::-1]:
                element_data = awkward.contents.RegularArray(element_data, int(s))

            return element_data

        else:  # ragged array
            offsets, element_raw_data = raw_data
            element_data = reconstruct_array(
                element_config,
                element_raw_data,
            )
            return ak.contents.ListOffsetArray(
                ak.index.Index64(offsets),
                element_data,
            )


class NBytesVersionFactory(BaseFactory):
    """
    Reads fNBytes, fVersion and check fNBytes. This factory
    and corresponding reader will not return anything. If
    you need information about fNBytes and fVersion, you
    should read them by yourself.

    This factory can only be created by other factory. It
    will never match items.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Never match items. If one needs to use this factory,
        create configuration like:

        - `factory`: `NBytesVersionFactory`
        - `name`: Name of the factory
        - `element_config`: Tree configuration of its element.
        """
        return None

    @classmethod
    def build_cpp_reader(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        element_config = tree_config["element_config"]
        element_reader = build_cpp_reader(element_config)
        return uproot_custom.cpp.NBytesVersionReader(
            tree_config["name"],
            element_reader,
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        """
        Directly return its reconstructed element array.
        """
        if tree_config["factory"] is not cls:
            return None

        element_config = tree_config["element_config"]
        return reconstruct_array(element_config, raw_data)


class GroupFactory(BaseFactory):
    """
    This factory groups differernt factory together. You can use
    this factory to read specific format of data as you like.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        Never match items. If one needs to use this factory,
        create configuration like:

        - `factory`: `GroupFactory`
        - `name`: Name of the factory
        - `sub_configs`: List of configurations of sub-readers.
        """
        return None

    @classmethod
    def build_cpp_reader(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        sub_readers = [build_cpp_reader(s) for s in tree_config["sub_configs"]]
        return uproot_custom.cpp.GroupReader(tree_config["name"], sub_readers)

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        sub_configs = tree_config["sub_configs"]

        sub_fields = []
        sub_contents = []
        for s_cfg, s_data in zip(sub_configs, raw_data):
            if s_cfg["factory"] is TObjectFactory and not s_cfg["keep_data"]:
                continue

            sub_fields.append(s_cfg["name"])
            sub_contents.append(reconstruct_array(s_cfg, s_data))

        return awkward.contents.RecordArray(sub_contents, sub_fields)


class BaseObjectFactory(BaseFactory):
    """
    This class reads base-object of an object. The base object has
    fNBytes(uint32), fVersion(uint16) at the beginning.
    """

    @classmethod
    def gen_tree_config(
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
        sub_streamers: list = all_streamer_info[fName]

        sub_configs = [gen_tree_config(s, all_streamer_info, item_path) for s in sub_streamers]

        return {
            "factory": cls,
            "name": fName,
            "sub_configs": sub_configs,
        }

    @classmethod
    def build_cpp_reader(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        name = tree_config["name"]
        sub_configs = tree_config["sub_configs"]

        # Combine NBytesVersionFactory and GroupFactory
        return build_cpp_reader(
            {
                "factory": NBytesVersionFactory,
                "name": name,
                "element_config": {
                    "factory": GroupFactory,
                    "name": name,
                    "sub_configs": sub_configs,
                },
            }
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        name = tree_config["name"]
        sub_configs = tree_config["sub_configs"]

        return reconstruct_array(
            {
                "factory": NBytesVersionFactory,
                "name": name,
                "element_config": {
                    "factory": GroupFactory,
                    "name": name,
                    "sub_configs": sub_configs,
                },
            },
            raw_data,
        )


class ObjectHeaderFactory(BaseFactory):
    """
    This class reads object header:
    1. fNBytes
    2. fTag
    3. if (fTag == -1) null-terminated-string

    If will be called automatically if no other factory matches.
    Also, it can be manually used to read object header.
    """

    @classmethod
    def priority(cls):
        return 0  # should be called last

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cur_streamer_info,
        all_streamer_info,
        item_path,
        **kwargs,
    ):
        """
        This factory will always match items. The returned configuration contains:
        - `factory`: cls
        - `name`: top_type_name
        - `element_config`: Configuration of the element factory/reader.
        """
        sub_streamers: list = all_streamer_info[top_type_name]
        sub_configs = [gen_tree_config(s, all_streamer_info, item_path) for s in sub_streamers]

        return {
            "factory": cls,
            "name": top_type_name,
            "element_config": {
                "factory": GroupFactory,
                "name": top_type_name,
                "sub_configs": sub_configs,
            },
        }

    @classmethod
    def build_cpp_reader(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        element_config = tree_config["element_config"]
        element_reader = build_cpp_reader(element_config)
        return uproot_custom.cpp.ObjectHeaderReader(
            tree_config["name"],
            element_reader,
        )

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        element_config = tree_config["element_config"]
        return reconstruct_array(element_config, raw_data)


class EmptyFactory(BaseFactory):
    """
    This factory does nothing. It's just a place holder.
    """

    @classmethod
    def build_cpp_reader(cls, tree_config):
        if tree_config["factory"] is not cls:
            return None

        return uproot_custom.cpp.EmptyReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, tree_config, raw_data):
        if tree_config["factory"] is not cls:
            return None

        return awkward.contents.EmptyArray()


registered_factories |= {
    BasicTypeFactory,
    STLSeqFactory,
    STLMapFactory,
    STLStringFactory,
    TArrayFactory,
    TStringFactory,
    TObjectFactory,
    CStyleArrayFactory,
    NBytesVersionFactory,
    GroupFactory,
    BaseObjectFactory,
    ObjectHeaderFactory,
    EmptyFactory,
}
