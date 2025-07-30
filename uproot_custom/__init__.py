import uproot
import uproot.behaviors.TBranch
import uproot.interpretation.identify

from .AsBinary import AsBinary
from .AsCustom import AsCustom, regularize_object_path
from .readers import (
    BaseReader,
    BasicTypeReader,
    CArrayReader,
    EmptyReader,
    ObjectReader,
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

##########################################################################################
#                                       Wrappers
##########################################################################################
_is_TBranchElement_branches_wrapped = False
_is_uproot_interpretation_of_wrapped = False

_uproot_interpretation_of = uproot.interpretation.identify.interpretation_of


def custom_interpretation_of(
    branch: uproot.behaviors.TBranch.TBranch, context: dict, simplify: bool = True
) -> uproot.interpretation.Interpretation:
    if not hasattr(branch, "parent"):
        return _uproot_interpretation_of(branch, context, simplify)

    if AsCustom.match_branch(branch, context, simplify):
        return AsCustom(branch, context, simplify)

    return _uproot_interpretation_of(branch, context, simplify)


def wrap_uproot_interpretation():
    global _is_uproot_interpretation_of_wrapped
    if not _is_uproot_interpretation_of_wrapped:
        _is_uproot_interpretation_of_wrapped = True
        uproot.interpretation.identify.interpretation_of = custom_interpretation_of


wrap_uproot_interpretation()
