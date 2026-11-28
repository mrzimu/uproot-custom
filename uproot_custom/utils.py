from __future__ import annotations

import re
from collections.abc import Iterable

import uproot.behaviors.TBranch

from uproot_custom.consts import (
    STL_VERSION_WITH_VALUE_VERSION,
    STL_VERSION_WITH_VALUE_VERSION_POINTER,
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


def _has_pointer_spelling(type_name: str | None) -> bool:
    """
    Tell whether a type name ends with the pointer marker.

    ROOT marks a pointer member with a trailing `*` in `fTypeName`
    (`TStreamerSTL::IsaPointer`), whatever the element class.  Both helpers
    below read that marker, so it is spelled once here.

    Args:
        type_name: a type name as the streamer info spells it, or `None`.

    Returns:
        `True` when a `*` ends the name, trailing spaces ignored.
    """
    return (type_name or "").rstrip().endswith("*")


def get_stl_value_version_min(cur_streamer_info: dict) -> int:
    """
    Get the frame version from which an STL element carries the value version.

    A collection (`kSTL`) reads it from version 8 and a pointer to one
    (`kSTLp`) only from 9 (`TStreamerInfoReadBuffer.cxx`, the `kSTL` and `kSTLp`
    cases).  The element does not record that distinction in `fType`, which is
    500 for every `TStreamerSTL` whatever the member (`StreamerInfo.md` §10);
    it marks the pointer with a trailing `*` in `fTypeName`
    (`TStreamerSTL::IsaPointer`) and with `kOffsetP` added to `fSTLtype`
    (`Collections.md` §11.3).  A pointer to a collection puts the same bytes on
    disk as the collection itself, so the boundary is all that differs.

    Args:
        cur_streamer_info: the streamer-info mapping of the STL element.

    Returns:
        The lowest frame version that carries the value class's version.
    """
    if _has_pointer_spelling(cur_streamer_info.get("fTypeName")):
        return STL_VERSION_WITH_VALUE_VERSION_POINTER
    return STL_VERSION_WITH_VALUE_VERSION


def is_pointer_to_collection(cur_streamer_info: dict) -> bool:
    """
    Tell whether an element is a pointer to an STL container (`kSTLp`).

    Only a `TStreamerSTL`-family element carries `fSTLtype`, and it records the
    pointer as a trailing `*` in its type name
    (`TStreamerSTL::IsaPointer`, `Collections.md` §11.3). Such a member is
    written as the container itself -- no pointer tag and no null marker -- so
    it must not be read as an object pointer; a null pointer is a count of 0.

    Args:
        cur_streamer_info: the streamer-info mapping of the element.

    Returns:
        `True` when the element is a pointer to a collection.
    """
    if "fSTLtype" not in cur_streamer_info:
        return False
    return _has_pointer_spelling(cur_streamer_info.get("fTypeName"))


def _drop_pointer_marker(type_name: str) -> str:
    """
    Strip the spelling noise from a type name and drop a trailing pointer.

    Args:
        type_name: a type name as the streamer info spells it.

    Returns:
        The name without `std::`, without the spacing ROOT varies on, and
        without a trailing `*`, which marks a pointer to the type.
    """
    type_name = type_name.replace("std::", "").replace("< ", "<").replace(" >", ">").strip()
    return re.sub(r"\s*\*+$", "", type_name)


def get_sequence_element_typename(type_name: str) -> str:
    """
    Get the element type name of a vector type.

    A pointer to a collection is stored as the collection itself, with no
    pointer tag and no null marker (`Collections.md` §11.3), so a trailing `*`
    is dropped.

    e.g. vector<vector<int>> -> vector<int>, vector<int>* -> int
    """
    type_name = _drop_pointer_marker(type_name)

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

    A trailing `*`, the mark of a pointer to the map, is dropped for the same
    reason as in `get_sequence_element_typename`.

    e.g. map<int, vector<int>> -> (int, vector<int>)
    """
    type_name = _drop_pointer_marker(type_name)

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
