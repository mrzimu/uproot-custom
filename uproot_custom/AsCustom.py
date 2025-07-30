from __future__ import annotations

import re

import numpy as np
import uproot
import uproot.behaviors.TBranch
import uproot.interpretation

from .readers import read_branch


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


class AsCustom(uproot.interpretation.Interpretation):
    target_branches: set[str] = set()

    def __init__(
        self,
        branch: uproot.behaviors.TBranch.TBranch,
        context: dict,
        simplify: bool,
    ):
        """
        Args:
            branch (:doc:`uproot.behaviors.TBranch.TBranch`): The ``TBranch`` to
                interpret as an array.
            context (dict): Auxiliary data used in deserialization.
            simplify (bool): If True, call
                :ref:`uproot.interpretation.objects.AsObjects.simplify` on any
                :doc:`uproot.interpretation.objects.AsObjects` to try to get a
                more efficient interpretation.

        Accept arguments from `uproot.interpretation.identify.interpretation_of`.
        """
        self._branch = branch
        self._context = context
        self._simplify = simplify

        # simplify streamer information
        self.all_streamer_info: dict[str, list[dict]] = {}
        for k, v in branch.file.streamers.items():
            cur_infos = [i.all_members for i in next(iter(v.values())).member("fElements")]
            self.all_streamer_info[k] = cur_infos

    @classmethod
    def match_branch(
        cls,
        branch: uproot.behaviors.TBranch.TBranch,
        context: dict,
        simplify: bool,
    ) -> bool:
        """
        Args:
            branch (:doc:`uproot.behaviors.TBranch.TBranch`): The ``TBranch`` to
                interpret as an array.
            context (dict): Auxiliary data used in deserialization.
            simplify (bool): If True, call
                :ref:`uproot.interpretation.objects.AsObjects.simplify` on any
                :doc:`uproot.interpretation.objects.AsObjects` to try to get a
                more efficient interpretation.

        Accept arguments from `uproot.interpretation.identify.interpretation_of`,
        determine whether this interpretation can be applied to the given branch.
        """
        full_path = regularize_object_path(branch.object_path)
        return full_path in cls.target_branches

    @property
    def typename(self) -> str:
        """
        The name of the type of the interpretation.
        """
        dims, is_jagged = get_dims_from_branch(self._branch)
        typename = self._branch.streamer.typename
        if dims:
            for i in dims:
                typename += f"[{i}]"
        return typename

    @property
    def cache_key(self) -> str:
        """
        The cache key of the interpretation.
        """
        return id(self)

    def __repr__(self) -> str:
        """
        The string representation of the interpretation.
        """
        return f"AsCustom({self.typename})"

    def final_array(
        self,
        basket_arrays,
        entry_start,
        entry_stop,
        entry_offsets,
        library,
        branch,
        options,
    ):
        """
        Concatenate the arrays from the baskets and return the final array.
        """

        awkward = uproot.extras.awkward()

        basket_entry_starts = np.array(entry_offsets[:-1])
        basket_entry_stops = np.array(entry_offsets[1:])

        basket_start_idx = np.where(basket_entry_starts <= entry_start)[0].max()
        basket_end_idx = np.where(basket_entry_stops >= entry_stop)[0].min()

        arr_to_concat = [basket_arrays[i] for i in range(basket_start_idx, basket_end_idx + 1)]
        tot_array = awkward.concatenate(arr_to_concat)

        relative_entry_start = entry_start - basket_entry_starts[basket_start_idx]
        relative_entry_stop = entry_stop - basket_entry_starts[basket_start_idx]

        return tot_array[relative_entry_start:relative_entry_stop]

    def basket_array(
        self,
        data,
        byte_offsets,
        basket,
        branch,
        context,
        cursor_offset,
        library,
        interp_options,
    ):
        assert library.name == "ak", "Only awkward arrays are supported"

        full_branch_path = regularize_object_path(branch.object_path)

        return read_branch(
            data,
            byte_offsets,
            branch.streamer.all_members,
            self.all_streamer_info,
            full_branch_path,
        )
