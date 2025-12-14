from __future__ import annotations

import awkward as ak
import numpy as np
import uproot
import uproot.behaviors.TBranch
import uproot.interpretation.custom
from uproot.behaviors.TBranch import _branch_clean_name

from uproot_custom.factories import read_branch, read_branch_awkward_form
from uproot_custom.utils import get_dims_from_branch, regularize_object_path


class AsCustom(uproot.interpretation.custom.CustomInterpretation):
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
        self._typename = None

        # try to fix streamer, due to a reverted PR https://github.com/scikit-hep/uproot5/pull/1505
        if branch.streamer is None:
            clean_name = _branch_clean_name.match(branch.name).group(2)
            fParentName = branch.member("fParentName", none_if_missing=True)
            fClassName = branch.member("fClassName", none_if_missing=True)

            if fParentName is not None and fParentName != "":
                matches = branch._file.streamers.get(fParentName.replace(" ", ""))

                if matches is not None:
                    streamerinfo = matches[max(matches)]

                    for element in streamerinfo.walk_members(branch._file.streamers):
                        if element.name == clean_name and (
                            fClassName is None
                            or fClassName == ""
                            or element.parent is None
                            or element.parent.name == ""
                            or element.parent.name == fClassName.replace(" ", "")
                        ):
                            branch._streamer = element
                            break

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
        if self._typename is None:
            dims, is_jagged = get_dims_from_branch(self._branch)
            typename = self._branch.streamer.typename

            if is_jagged:
                typename += "[]"

            if dims:
                for i in dims:
                    typename += f"[{i}]"
            self._typename = typename
        return self._typename

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
        basket_entry_starts = np.array(entry_offsets[:-1])
        basket_entry_stops = np.array(entry_offsets[1:])

        basket_start_idx = np.where(basket_entry_starts <= entry_start)[0].max()
        basket_end_idx = np.where(basket_entry_stops >= entry_stop)[0].min()

        arr_to_concat = [basket_arrays[i] for i in range(basket_start_idx, basket_end_idx + 1)]
        tot_array = ak.concatenate(arr_to_concat)

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
        assert branch is self._branch, "Branch mismatch"

        full_branch_path = regularize_object_path(self._branch.object_path)

        if self._branch.streamer is None:
            cls_streamer_info = {
                "fName": self._branch.name,
                "fTypeName": self.typename,
            }
        else:
            cls_streamer_info = self._branch.streamer.all_members

        return read_branch(
            self._branch,
            data,
            byte_offsets,
            cls_streamer_info,
            self.all_streamer_info,
            full_branch_path,
        )

    def awkward_form(
        self,
        file,
        context=None,
        index_format="i64",
        header=False,
        tobject_header=False,
        breadcrumbs=(),
    ):
        assert file is self._branch.file, "File mismatch"

        full_branch_path = regularize_object_path(self._branch.object_path)

        if self._branch.streamer is None:
            cls_streamer_info = {
                "fName": self._branch.name,
                "fTypeName": self.typename,
            }
        else:
            cls_streamer_info = self._branch.streamer.all_members

        return read_branch_awkward_form(
            self._branch,
            cls_streamer_info,
            self.all_streamer_info,
            full_branch_path,
        )
