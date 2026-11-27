from __future__ import annotations

import re
from collections.abc import Iterable

import uproot.behaviors.TBranch

from uproot_custom.consts import (
    STL_VERSION_WITH_VALUE_VERSION,
    STL_VERSION_WITH_VALUE_VERSION_POINTER,
    kSTLp,
)


def regularize_object_path(object_path: str) -> str:
    return re.sub(r";[0-9]+", r"", object_path)


def _regularized_paths(paths: str | Iterable[str], caller: str) -> tuple[str, ...]:
    """
    Regularize one object-path or an iterable of them.

    Args:
        paths: one object-path, or an iterable of them.
        caller: name of the public function, used in the error message.

    Returns:
        The paths without their cycle number.

    Raises:
        TypeError: if an item is not a `str`.
    """
    if isinstance(paths, str):
        paths = (paths,)

    regularized = []
    for cur in paths:
        if not isinstance(cur, str):
            raise TypeError(f"{caller}() takes object paths as str, not {type(cur).__name__}")
        regularized.append(regularize_object_path(cur))

    return tuple(regularized)


_title_has_dims = re.compile(r"^([^\[\]]*)(\[[^\[\]]+\])+")
_item_dim_pattern = re.compile(r"\[([1-9][0-9]*)\]")
_item_any_pattern = re.compile(r"(\[.*\])")


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
    type_name = type_name.replace("std::", "").strip()
    return type_name.split("<")[0]


def compile_type_name(type_name: str) -> str:
    """
    Normalize a ROOT type name so two spellings of one type compare equal.

    ROOT spells a template name with a space before the closing brackets when
    the parameter is itself a template (`map<int,string> `) and without one
    otherwise, so whitespace and the redundant `std::` are dropped.

    Args:
        type_name: a type name as the streamer info spells it.

    Returns:
        The comparable form.
    """
    return re.sub(r"\s+", "", type_name.replace("std::", ""))


def find_class_streamer_info(
    type_name: str, all_streamer_info: dict
) -> tuple[str, list[dict]] | None:
    """
    Find a class's element list by its type name.

    An exact lookup is tried first, because that is the spelling the file uses,
    and a whitespace-insensitive one after it (`compile_type_name`).

    Args:
        type_name: the class's name, e.g. `pair<int, vector<int>>`.
        all_streamer_info: streamer information of all types, keyed by name.

    Returns:
        The name as the file spells it and its element list, or `None` when no
        streamer info describes the class.
    """
    exact = all_streamer_info.get(type_name)
    if exact is not None:
        return type_name, exact

    wanted = compile_type_name(type_name)
    for name, elements in all_streamer_info.items():
        if compile_type_name(name) == wanted:
            return name, elements

    return None


def get_stl_value_version_min(fType: int | None) -> int:
    """
    Get the frame version from which an STL element carries the value version.

    `kSTL` reads it from version 8 and `kSTLp`, a pointer to the same container,
    only from 9 (`TStreamerInfoReadBuffer.cxx`, the `kSTL` and `kSTLp` cases).

    Args:
        fType: the streamer element's `fType`, or `None` when it has none.

    Returns:
        The lowest frame version that carries the value class's version.
    """
    if fType == kSTLp:
        return STL_VERSION_WITH_VALUE_VERSION_POINTER
    return STL_VERSION_WITH_VALUE_VERSION


def get_sequence_element_typename(type_name: str) -> str:
    """
    Get the element type name of a vector type.

    e.g. vector<vector<int>> -> vector<int>
    """
    type_name = type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()

    lt_idx = -1
    gt_idx = -1
    stack_level = 0

    for i, c in enumerate(type_name):
        if c == "<":
            stack_level += 1
            if stack_level == 1:
                lt_idx = i

        if c == ">":
            stack_level -= 1
            if stack_level == 0:
                gt_idx = i
                break

    if lt_idx == -1 or gt_idx == -1:
        raise ValueError(f"Invalid sequence type name: {type_name}")

    if gt_idx != len(type_name) - 1:
        raise ValueError(f"Invalid sequence type name: {type_name}")

    return type_name[lt_idx + 1 : gt_idx]


def get_map_key_val_typenames(type_name: str) -> tuple[str, str]:
    """
    Get the key and value type names of a map type.

    e.g. map<int, vector<int>> -> (int, vector<int>)
    """
    type_name = type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()

    lt_idx = -1
    gt_idx = -1
    split_idx = -1
    stack_level = 0

    for i, c in enumerate(type_name):
        if c == "<":
            stack_level += 1
            if stack_level == 1:
                lt_idx = i

        if c == "," and stack_level == 1:
            split_idx = i

        if c == ">":
            stack_level -= 1
            if stack_level == 0:
                gt_idx = i
                break

    if lt_idx == -1 or gt_idx == -1 or split_idx == -1:
        raise ValueError(f"Invalid map type name: {type_name}")

    if gt_idx != len(type_name) - 1:
        raise ValueError(f"Invalid map type name: {type_name}")

    key_type = type_name[lt_idx + 1 : split_idx].strip()
    val_type = type_name[split_idx + 1 : gt_idx].strip()

    return key_type, val_type


def get_pair_type_name(map_type_name: str) -> str:
    """
    Get the `pair` type name ROOT uses as the element of a map.

    A map's element is a `pair`, so `map<int, vector<int>>` is stored as a run
    of `pair<int, vector<int>>` values (`TGenCollectionProxy::GetValueClass`).

    Args:
        map_type_name: a map type name such as `map<int, vector<int>>`.

    Returns:
        The matching pair type name.
    """
    key_type_name, val_type_name = get_map_key_val_typenames(map_type_name)
    return f"pair<{key_type_name},{val_type_name}>"
