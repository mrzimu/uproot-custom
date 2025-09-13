import uproot
import uproot.behaviors.TBranch
import uproot.interpretation.identify

from uproot_custom.AsBinary import AsBinary
from uproot_custom.AsCustom import AsCustom
from uproot_custom.AsGroupedMap import AsGroupedMap
from uproot_custom.readers import (
    BaseObjectReader,
    BaseReader,
    BasicTypeReader,
    CArrayReader,
    EmptyReader,
    ObjectHeaderReader,
    STLMapReader,
    STLSeqReader,
    STLStringReader,
    TArrayReader,
    TObjectReader,
    TStringReader,
    gen_tree_config,
    get_cpp_reader,
    reconstruct_array,
    registered_readers,
)
from uproot_custom.utils import regularize_object_path

##########################################################################################
#                                       Wrappers
##########################################################################################
_is_uproot_interpretation_of_wrapped = False

_uproot_interpretation_of = uproot.interpretation.identify.interpretation_of


def custom_interpretation_of(
    branch: uproot.behaviors.TBranch.TBranch, context: dict, simplify: bool = True
) -> uproot.interpretation.Interpretation:
    if not hasattr(branch, "parent"):
        return _uproot_interpretation_of(branch, context, simplify)

    if AsGroupedMap.match_branch(branch, context, simplify):
        return AsGroupedMap(branch, context, simplify)

    if AsCustom.match_branch(branch, context, simplify):
        return AsCustom(branch, context, simplify)

    return _uproot_interpretation_of(branch, context, simplify)


def wrap_uproot_interpretation():
    global _is_uproot_interpretation_of_wrapped
    if not _is_uproot_interpretation_of_wrapped:
        _is_uproot_interpretation_of_wrapped = True
        uproot.interpretation.identify.interpretation_of = custom_interpretation_of


wrap_uproot_interpretation()
