from __future__ import annotations

import re

import uproot.behaviors.TBranch


def regularize_object_path(object_path: str) -> str:
    return re.sub(r";[0-9]+", r"", object_path)


_title_has_dims = re.compile(r"^([^\[\]]*)(\[[^\[\]]+\])+")
_item_dim_pattern = re.compile(r"\[([1-9][0-9]*)\]")
_item_any_pattern = re.compile(r"\[(.*)\]")


def get_dims_from_branch(
    branch: uproot.behaviors.TBranch.TBranch,
) -> tuple[tuple[int, ...], bool]:
    leaf = branch.member("fLeaves")[0]
    title = leaf.member("fTitle")

    dims, is_jagged = (), False

    m = _title_has_dims.match(title)
    if m is not None:
        dims = tuple(int(x) for x in re.findall(_item_dim_pattern, title))
        if dims == () and leaf.member("fLen") > 1:
            dims = (leaf.member("fLen"),)

        if any(
            _item_dim_pattern.match(x) is None for x in re.findall(_item_any_pattern, title)
        ):
            is_jagged = True

    return dims, is_jagged


def get_top_type_name(type_name: str) -> str:
    if type_name.endswith("*"):
        type_name = type_name[:-1].strip()
    type_name = type_name.replace("std::", "").strip()
    return type_name.split("<")[0]


def get_sequence_element_typename(type_name: str) -> str:
    """
    Get the element type name of a vector type.

    e.g. vector<vector<int>> -> vector<int>
    """
    type_name = type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()
    return re.match(r"^(vector|array|list|set|unordered_set)<(.*)>$", type_name).group(2)


def get_map_key_val_typenames(type_name: str) -> tuple[str, str]:
    """
    Get the key and value type names of a map type.

    e.g. map<int, vector<int>> -> (int, vector<int>)
    """
    type_name = type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()
    return re.match(r"^(map|unordered_map|multimap)<(.*),(.*)>$", type_name).groups()[1:3]
