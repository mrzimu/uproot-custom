"""
The uproot plumbing the `AsCustom` interpretation needs, and nothing else.

An uproot `Interpretation` has to answer five questions: does this branch match
(`match_branch`), what is its C++ type name, how is it cached, how are the
per-basket arrays joined, and what awkward form does it produce.  Answering them
means reading the branch's streamer info and building a factory -- none of which
depends on *how* the bytes are then decoded.

`AsCustom` keeps that plumbing and delegates the byte-level read to the reader
backend selected by `uproot_custom.backend`:

* `cpp` -- the pybind11 readers in `uproot_custom.cpp` (the default);
* `python` -- the pure-Python readers in `uproot_custom.python`;
* `forth` -- the experimental Forth readers in `uproot_custom._forth`;
* `detree` -- declarative readers in `uproot_custom.detree`, compiled to a
  detree-vm module and executed on a Detree machine.

A factory is the same on every backend: it decides which reader to build and
how the raw data becomes an awkward array.  Only the byte-level reader differs,
so a branch must produce the same array whichever backend runs it.
"""

from __future__ import annotations

from typing import ClassVar

import awkward as ak
import numpy as np
import uproot
import uproot.behaviors.TBranch
import uproot.interpretation.custom
from uproot.behaviors.TBranch import _branch_clean_name

from uproot_custom.backend import get_backend
from uproot_custom.factories import Factory, build_factory
from uproot_custom.utils import get_dims_from_branch, regularize_object_path


class AsCustom(uproot.interpretation.custom.CustomInterpretation):
    """
    The branch, its streamer info, and the factory built from them.

    A subclass supplies its own `basket_array`; everything else is here.
    """

    #: Branches this interpretation claims, as regularized object paths.  This
    #: set is the storage behind `uproot_custom.claim`; claim branches through
    #: that function rather than by writing here, so the cycle number is
    #: regularized and the argument type is checked.
    target_branches: ClassVar[set[str]] = set()

    def __init__(
        self,
        branch: uproot.behaviors.TBranch.TBranch,
        context: dict,
        simplify: bool,
    ):
        """
        Interpret one branch as an array.

        The arguments come from
        `uproot.interpretation.identify.interpretation_of`.

        Args:
            branch: the `TBranch` to interpret as an array.
            context: auxiliary data used in deserialization.
            simplify: if True, call
                `uproot.interpretation.objects.AsObjects.simplify` on any
                `uproot.interpretation.objects.AsObjects` to try to get a
                more efficient interpretation.
        """
        self._branch = branch
        self._context = context
        self._simplify = simplify
        self._typename = None
        self._factory: Factory | None = None
        self._compiled_detree_codes = None

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

        self.cls_streamer_info: dict = {}
        if self._branch.streamer is None:
            self.cls_streamer_info = {
                "fName": self._branch.name,
                "fTypeName": self.typename,
            }
        else:
            self.cls_streamer_info = self._branch.streamer.all_members

    @classmethod
    def match_branch(
        cls,
        branch: uproot.behaviors.TBranch.TBranch,
        context: dict,
        simplify: bool,
    ) -> bool:
        """
        Return whether this interpretation applies to *branch*.

        The arguments come from
        `uproot.interpretation.identify.interpretation_of`.

        Args:
            branch: the `TBranch` to interpret as an array.
            context: auxiliary data used in deserialization.
            simplify: if True, call
                `uproot.interpretation.objects.AsObjects.simplify` on any
                `uproot.interpretation.objects.AsObjects` to try to get a
                more efficient interpretation.

        Returns:
            True when the branch's regularized object path is registered for
            this interpretation.
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

    @property
    def factory(self) -> Factory:
        if self._factory is None:
            full_branch_path = regularize_object_path(self._branch.object_path)

            self._factory = build_factory(
                cur_streamer_info=self.cls_streamer_info,
                all_streamer_info=self.all_streamer_info,
                item_path=full_branch_path,
                called_from_top=True,
                branch=self._branch,
            )

        return self._factory

    def __repr__(self) -> str:
        """
        The string representation of the interpretation.
        """
        return f"{type(self).__name__}({self.typename})"

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

        return ak.to_packed(tot_array[relative_entry_start:relative_entry_stop])

    def basket_array(
        self,
        data: np.ndarray,
        byte_offsets: np.ndarray,
        basket,
        branch,
        context,
        cursor_offset,
        library,
        interp_options,
    ):
        assert library.name == "ak", "Only awkward arrays are supported"
        assert branch is self._branch, "Branch mismatch"

        nbyte = self.cls_streamer_info.get("fSize")
        if byte_offsets is None:
            if nbyte is None:
                raise ValueError("nbyte must be specified if offsets is None")
            byte_offsets = np.arange(data.size // nbyte + 1, dtype=np.uint32) * nbyte

        backend_val = get_backend()

        if backend_val == "cpp":
            import uproot_custom.cpp

            reader = self.factory.build_cpp_reader()
            raw_data = uproot_custom.cpp.read_data(data, byte_offsets, cursor_offset, reader)

        elif backend_val == "python":
            import uproot_custom.python

            reader = self.factory.build_python_reader()
            raw_data = uproot_custom.python.read_data(
                data, byte_offsets, cursor_offset, reader
            )

        elif backend_val == "forth":
            import warnings

            import uproot_custom._forth

            warnings.warn(
                '"forth" reader is only for testing and benchmarking. It is not recommended for production use.',
                UserWarning,
            )

            buffer_holder = uproot_custom._forth.BufferHolder()
            reader = self.factory.build_forth_reader(buffer_holder)
            raw_data = uproot_custom._forth.read_data(data, byte_offsets, reader)

        elif backend_val == "detree":
            from uproot_custom.detree.run import apply_outputs, compiled_for_reader, run

            reader = self.factory.build_detree_reader()
            if self._compiled_detree_codes is None:
                self._compiled_detree_codes = compiled_for_reader(reader)

            outputs, states = run(
                self._compiled_detree_codes,
                data,
                byte_offsets,
                cursor_offset,
                nbyte=self.cls_streamer_info.get("fSize"),
            )

            apply_outputs(reader, outputs, states)
            raw_data = reader.data()

        else:
            raise ValueError(f"Unknown reader backend: {backend_val}.")

        return self.factory.make_awkward_content(raw_data)

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

        return self.factory.make_awkward_form()


__all__ = ["AsCustom"]
