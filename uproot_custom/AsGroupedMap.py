from __future__ import annotations

import uproot
import uproot.behaviors.TBranch
import uproot.behaviors.TBranchElement
import uproot.interpretation

from uproot_custom.AsCustom import AsCustom
from uproot_custom.utils import (
    get_map_key_val_typenames,
    regularize_object_path,
)


class AsGroupedMap(uproot.interpretation.Interpretation):
    target_branches: set[str] = set()

    subbranches: dict[
        str,
        tuple[
            uproot.behaviors.TBranchElement.TBranchElement,
            uproot.behaviors.TBranchElement.TBranchElement,
        ],
    ] = {}

    def __init__(
        self,
        branch: uproot.behaviors.TBranch.TBranch,
        context: dict,
        simplify: bool,
    ):
        self._branch = branch
        self._context = context
        self._simplify = simplify

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
        if full_path not in cls.target_branches:
            return False

        # 1:vector, 2:list, 3:deque, 4:map, 5:set, 6:multimap, 7:multiset, 12:unordered_map
        stl_type = branch.streamer.stl_type
        assert stl_type in (
            4,
            6,
            12,
        ), f"Only map and multimap are supported in AsGroupedMap, but got {stl_type}."

        key_type_name, val_type_name = get_map_key_val_typenames(branch.streamer.typename)

        key_branch = branch.branches[0]
        val_branch = branch.branches[1]

        key_branch._interpretation = AsCustom(
            key_branch,
            context,
            simplify,
            typename=key_type_name + "[]",
        )

        val_branch._interpretation = AsCustom(
            val_branch,
            context,
            simplify,
            typename=val_type_name + "[]",
        )

        return False
