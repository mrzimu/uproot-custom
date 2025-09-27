from __future__ import annotations

import uproot
import uproot.behaviors.TBranch

from uproot_custom.AsCustom import AsCustom
from uproot_custom.utils import get_map_key_val_typenames


class AsGroupedMap(AsCustom):
    target_branches: set[str] = set()

    def __init__(
        self,
        branch: uproot.behaviors.TBranch.TBranch,
        context: dict,
        simplify: bool,
    ):
        AsCustom.__init__(self, branch, context, simplify)

        # 1:vector, 2:list, 3:deque, 4:map, 5:set, 6:multimap, 7:multiset, 12:unordered_map
        stl_type = branch.parent.streamer.stl_type
        assert stl_type in (
            4,
            6,
            12,
        ), f"Only map and multimap are supported for STL grouped branches, but got {stl_type}."

        key_type_name, val_type_name = get_map_key_val_typenames(
            branch.parent.streamer.typename
        )

        if branch == branch.parent.branches[0]:
            self._typename = key_type_name + "[]"

        elif branch == branch.parent.branches[1]:
            self._typename = val_type_name + "[]"

        else:
            raise ValueError(
                f"Branch {branch.name} not found in its parent branch {branch.parent.name}."
            )
