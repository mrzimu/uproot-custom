from __future__ import annotations

import re
from typing import Union

import awkward as ak
import awkward.contents
import awkward.index
import numpy as np

from . import _cpp

registered_readers: set[type["BaseReader"]] = set()


def get_top_type_name(type_name: str) -> str:
    if type_name.endswith("*"):
        type_name = type_name[:-1].strip()
    type_name = type_name.replace("std::", "").strip()
    return type_name.split("<")[0]


def gen_tree_config(
    cls_streamer_info: dict,
    all_streamer_info: dict,
    item_path: str,
    called_from_top: bool = False,
) -> dict:
    """
    Generate reader configuration for a class streamer information.

    The content it returns should be:

    ```python
    {
        "reader": ReaderType,
        "name": str,
        "ctype": str, # for CTypeReader, TArrayReader
        "element_reader": dict, # reader config of the element, for STLVectorReader, SimpleCArrayReader, TObjectCArrayReader
        "flat_size": int, # for SimpleCArrayReader, TObjectCArrayReader
        "fMaxIndex": list[int], # for SimpleCArrayReader, TObjectCArrayReader
        "fArrayDim": int, # for SimpleCArrayReader, TObjectCArrayReader
        "key_reader": dict, # reader config of the key, for STLMapReader
        "val_reader": dict, # reader config of the value, for STLMapReader
        "sub_readers": list[dict], # for ObjectReader, ObjectHeaderReader
        "is_top_level": bool, # for STLVectorReader, STLMapReader, STLStringReader
    }
    ```

    Args:
        cls_streamer_info (dict): Class streamer information.
        all_streamer_info (dict): All streamer information.
        item_path (str): Path to the item.

    Returns:
        dict: Reader configuration.
    """
    fName = cls_streamer_info["fName"]

    top_type_name = (
        get_top_type_name(cls_streamer_info["fTypeName"])
        if "fTypeName" in cls_streamer_info
        else None
    )

    if not called_from_top:
        item_path = f"{item_path}.{fName}"

    for reader in sorted(registered_readers, key=lambda x: x.priority(), reverse=True):
        tree_config = reader.gen_tree_config(
            top_type_name,
            cls_streamer_info,
            all_streamer_info,
            item_path,
        )
        if tree_config is not None:
            return tree_config

    raise ValueError(f"Unknown type: {cls_streamer_info['fTypeName']} for {item_path}")


def get_cpp_reader(tree_config: dict):
    for reader in sorted(registered_readers, key=lambda x: x.priority(), reverse=True):
        cpp_reader = reader.get_cpp_reader(tree_config)
        if cpp_reader is not None:
            return cpp_reader

    raise ValueError(f"Unknown reader type: {tree_config['reader']} for {tree_config['name']}")


def reconstruct_array(
    raw_data: Union[np.ndarray, tuple, list, None],
    tree_config: dict,
) -> Union[ak.Array, None]:
    for reader in sorted(registered_readers, key=lambda x: x.priority(), reverse=True):
        data = reader.reconstruct_array(raw_data, tree_config)
        if data is not None:
            return data

    raise ValueError(f"Unknown reader type: {tree_config['reader']} for {tree_config['name']}")


def read_branch(
    data: np.ndarray[np.uint8],
    offsets: np.ndarray,
    cls_streamer_info: dict,
    all_streamer_info: dict[str, list[dict]],
    item_path: str = "",
):
    tree_config = gen_tree_config(cls_streamer_info, all_streamer_info, item_path)
    reader = get_cpp_reader(tree_config)

    if offsets is None:
        nbyte = cls_streamer_info["fSize"]
        offsets = np.arange(data.size // nbyte + 1, dtype=np.uint32) * nbyte
    raw_data = _cpp.read_data(data, offsets, reader)

    return reconstruct_array(raw_data, tree_config)


class BaseReader:
    @classmethod
    def priority(cls) -> int:
        """
        Return the priority of the reader. Readers with higher priority will be called first.
        """
        return 10

    @classmethod
    def gen_tree_config(
        cls,
        cls_streamer_info: dict,
        all_streamer_info: dict,
        item_path: str = "",
    ) -> dict:
        raise NotImplementedError("This method should be implemented in subclasses.")

    @classmethod
    def get_cpp_reader(cls, tree_config: dict) -> Union["BaseReader", None]:
        """
        Args:
            tree_config (dict): The configuration dictionary for the reader.

        Returns:
            BaseReader: An instance of the appropriate reader class.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @classmethod
    def reconstruct_array(
        cls,
        raw_data: Union[np.ndarray, tuple, list, None],
        tree_config: dict,
    ) -> Union[ak.Array, None]:
        """
        Args:
            raw_data (Union[np.ndarray, tuple, list, None]): The raw data to be
                recovered.
            tree_config (dict): The configuration dictionary for the reader.

        Returns:
            ak.Array: The recovered data as an ak array.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")


class BasicTypeReader(BaseReader):
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
        "bool": _cpp.BoolReader,
        "i1": _cpp.Int8Reader,
        "i2": _cpp.Int16Reader,
        "i4": _cpp.Int32Reader,
        "i8": _cpp.Int64Reader,
        "u1": _cpp.UInt8Reader,
        "u2": _cpp.UInt16Reader,
        "u4": _cpp.UInt32Reader,
        "u8": _cpp.UInt64Reader,
        "f": _cpp.FloatReader,
        "d": _cpp.DoubleReader,
    }

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name in BasicTypeReader.typenames:
            ctype = BasicTypeReader.typenames[top_type_name]
            return {
                "reader": cls,
                "name": cls_streamer_info["fName"],
                "ctype": ctype,
            }
        else:
            return None

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        ctype = tree_config["ctype"]
        return cls.cpp_reader_map[ctype](tree_config["name"])

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
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
}


class STLSeqReader(BaseReader):
    @staticmethod
    def get_sequence_element_typename(type_name: str) -> str:
        """
        Get the element type name of a vector type.

        e.g. vector<vector<int>> -> vector<int>
        """
        type_name = (
            type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()
        )
        return re.match(r"^(vector|array)<(.*)>$", type_name).group(2)

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name not in ["vector", "array"]:
            return None

        fName = cls_streamer_info["fName"]
        fTypeName = cls_streamer_info["fTypeName"]
        element_type = cls.get_sequence_element_typename(fTypeName)
        element_info = {
            "fName": fName,
            "fTypeName": element_type,
        }

        element_tree_config = gen_tree_config(
            element_info,
            all_streamer_info,
            item_path,
        )

        top_element_type = get_top_type_name(element_type)
        if top_element_type in stl_typenames:
            element_tree_config["is_top"] = False

        return {
            "reader": cls,
            "name": fName,
            "element_reader": element_tree_config,
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        element_cpp_reader = get_cpp_reader(tree_config["element_reader"])
        is_top = tree_config.get("is_top", True)
        return _cpp.STLSeqReader(
            tree_config["name"],
            is_top,
            element_cpp_reader,
        )

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        offsets, element_raw_data = raw_data
        element_data = reconstruct_array(
            element_raw_data,
            tree_config["element_reader"],
        )

        return ak.contents.ListOffsetArray(
            ak.index.Index64(offsets),
            element_data,
        )


class STLMapReader(BaseReader):
    """
    This class reads std::map from a binary parser.
    """

    @staticmethod
    def get_map_key_val_typenames(type_name: str) -> tuple[str, str]:
        """
        Get the key and value type names of a map type.

        e.g. map<int, vector<int>> -> (int, vector<int>)
        """
        type_name = (
            type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()
        )
        return re.match(r"^(map|unordered_map|multimap)<(.*),(.*)>$", type_name).groups()[1:3]

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name not in ["map", "unordered_map", "multimap"]:
            return None

        fTypeName = cls_streamer_info["fTypeName"]
        key_type_name, val_type_name = cls.get_map_key_val_typenames(fTypeName)

        fName = cls_streamer_info["fName"]
        key_info = {
            "fName": "key",
            "fTypeName": key_type_name,
        }

        val_info = {
            "fName": "val",
            "fTypeName": val_type_name,
        }

        key_tree_config = gen_tree_config(key_info, all_streamer_info, item_path)
        if get_top_type_name(key_type_name) in stl_typenames:
            key_tree_config["is_top"] = False

        val_tree_config = gen_tree_config(val_info, all_streamer_info, item_path)
        if get_top_type_name(val_type_name) in stl_typenames:
            val_tree_config["is_top"] = False

        return {
            "reader": cls,
            "name": fName,
            "key_reader": key_tree_config,
            "val_reader": val_tree_config,
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        key_cpp_reader = get_cpp_reader(tree_config["key_reader"])
        val_cpp_reader = get_cpp_reader(tree_config["val_reader"])
        is_top = tree_config.get("is_top", True)
        return _cpp.STLMapReader(
            tree_config["name"],
            is_top,
            key_cpp_reader,
            val_cpp_reader,
        )

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        key_tree_config = tree_config["key_reader"]
        val_tree_config = tree_config["val_reader"]
        offsets, key_raw_data, val_raw_data = raw_data
        key_data = reconstruct_array(key_raw_data, key_tree_config)
        val_data = reconstruct_array(val_raw_data, val_tree_config)

        return ak.contents.ListOffsetArray(
            ak.index.Index64(offsets),
            ak.contents.RecordArray(
                [key_data, val_data],
                [key_tree_config["name"], val_tree_config["name"]],
            ),
        )


class STLStringReader(BaseReader):
    """
    This class reads std::string from a binary parser.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name != "string":
            return None

        return {
            "reader": cls,
            "name": cls_streamer_info["fName"],
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        return _cpp.STLStringReader(
            tree_config["name"],
            tree_config.get("is_top", True),
        )

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data, parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )


class TArrayReader(BaseReader):
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
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name not in cls.typenames:
            return None

        ctype = cls.typenames[top_type_name]
        return {
            "reader": cls,
            "name": cls_streamer_info["fName"],
            "ctype": ctype,
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        ctype = tree_config["ctype"]

        return {
            "i1": _cpp.TArrayCReader,
            "i2": _cpp.TArraySReader,
            "i4": _cpp.TArrayIReader,
            "i8": _cpp.TArrayLReader,
            "f": _cpp.TArrayFReader,
            "d": _cpp.TArrayDReader,
        }[ctype](tree_config["name"])

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data),
        )


class TStringReader(BaseReader):
    """
    This class reads TString from a binary parser.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name != "TString":
            return None

        return {
            "reader": cls,
            "name": cls_streamer_info["fName"],
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        return _cpp.TStringReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        offsets, data = raw_data
        return awkward.contents.ListOffsetArray(
            awkward.index.Index64(offsets),
            awkward.contents.NumpyArray(data, parameters={"__array__": "char"}),
            parameters={"__array__": "string"},
        )


class TObjectReader(BaseReader):
    """
    This class reads TObject from a binary parser.

    It will not record any data.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name != "BASE":
            return None

        fType = cls_streamer_info["fType"]
        if fType != 66:
            return None

        return {
            "reader": cls,
            "name": cls_streamer_info["fName"],
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        return _cpp.TObjectReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        return None


class CArrayReader(BaseReader):
    """
    This class reads a C-array from a binary parser.
    """

    @classmethod
    def priority(cls):
        return 20  # This reader should be called first

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if cls_streamer_info.get("fArrayDim", 0) == 0:
            return None

        fName = cls_streamer_info["fName"]
        fTypeName = cls_streamer_info["fTypeName"]
        fArrayDim = cls_streamer_info["fArrayDim"]
        fMaxIndex = cls_streamer_info["fMaxIndex"]

        element_streamer_info = cls_streamer_info.copy()
        element_streamer_info["fArrayDim"] = 0

        element_tree_config = gen_tree_config(
            element_streamer_info,
            all_streamer_info,
        )

        flat_size = np.prod(fMaxIndex[:fArrayDim])
        assert flat_size > 0, f"flatten_size should be greater than 0, but got {flat_size}"

        # c-type number or TArray
        if (
            top_type_name in BasicTypeReader.typenames
            or top_type_name in TArrayReader.typenames
        ):
            return {
                "reader": cls,
                "name": fName,
                "is_obj": False,
                "element_reader": element_tree_config,
                "flat_size": flat_size,
                "fMaxIndex": fMaxIndex,
                "fArrayDim": fArrayDim,
            }

        # TSTring
        elif top_type_name == "TString":
            return {
                "reader": cls,
                "name": fName,
                "is_obj": True,
                "element_reader": element_tree_config,
                "flat_size": flat_size,
                "fMaxIndex": fMaxIndex,
                "fArrayDim": fArrayDim,
            }

        # STL
        elif top_type_name in stl_typenames:
            element_tree_config["is_top"] = False
            return {
                "reader": cls,
                "name": fName,
                "is_obj": True,
                "flat_size": flat_size,
                "element_reader": element_tree_config,
                "fMaxIndex": fMaxIndex,
                "fArrayDim": fArrayDim,
            }

        else:
            raise ValueError(f"Unknown type: {top_type_name} for C-array: {fTypeName}")

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        reader_type = tree_config["reader"]
        if reader_type is not cls:
            return None

        element_reader = get_cpp_reader(tree_config["element_reader"])

        return _cpp.CArrayReader(
            tree_config["name"],
            tree_config["is_obj"],
            tree_config["flat_size"],
            element_reader,
        )

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        element_tree_config = tree_config["element_reader"]
        fMaxIndex = tree_config["fMaxIndex"]
        fArrayDim = tree_config["fArrayDim"]
        shape = [fMaxIndex[i] for i in range(fArrayDim)]

        element_data = reconstruct_array(
            raw_data,
            element_tree_config,
        )

        for s in shape[::-1]:
            element_data = awkward.contents.RegularArray(element_data, int(s))

        return element_data


class ObjectReader(BaseReader):
    """
    It has fNBytes(uint32), fVersion(uint16) at the beginning.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        if top_type_name != "BASE":
            return None

        fType = cls_streamer_info["fType"]
        if fType != 0:
            return None

        fName = cls_streamer_info["fName"]
        sub_streamers: list = all_streamer_info[fName]

        sub_tree_configs = [
            gen_tree_config(s, all_streamer_info, item_path) for s in sub_streamers
        ]

        return {
            "reader": cls,
            "name": fName,
            "sub_readers": sub_tree_configs,
        }

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        sub_readers = [get_cpp_reader(s) for s in tree_config["sub_readers"]]
        return _cpp.ObjectReader(tree_config["name"], sub_readers)

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        sub_tree_configs = tree_config["sub_readers"]

        arr_dict = {}
        for s_cfg, s_data in zip(sub_tree_configs, raw_data):
            s_name = s_cfg["name"]
            s_reader_type = s_cfg["reader"]

            if s_reader_type == TObjectReader:
                continue

            arr_dict[s_name] = reconstruct_array(s_data, s_cfg)

        return awkward.contents.RecordArray(
            [arr_dict[k] for k in arr_dict],
            [k for k in arr_dict],
        )


class EmptyReader(BaseReader):
    """
    This class does nothing.
    """

    @classmethod
    def gen_tree_config(
        cls,
        top_type_name,
        cls_streamer_info,
        all_streamer_info,
        item_path,
    ):
        return None

    @classmethod
    def get_cpp_reader(cls, tree_config: dict):
        if tree_config["reader"] is not cls:
            return None

        return _cpp.EmptyReader(tree_config["name"])

    @classmethod
    def reconstruct_array(cls, raw_data, tree_config):
        if tree_config["reader"] is not cls:
            return None

        return awkward.contents.EmptyArray()


registered_readers |= {
    BasicTypeReader,
    STLSeqReader,
    STLMapReader,
    STLStringReader,
    TArrayReader,
    TStringReader,
    TObjectReader,
    CArrayReader,
    ObjectReader,
    EmptyReader,
}
