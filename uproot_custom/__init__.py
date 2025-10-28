from __future__ import annotations

import uproot

from uproot_custom.AsCustom import AsCustom
from uproot_custom.factories import (
    AnyClassFactory,
    BaseObjectFactory,
    CStyleArrayFactory,
    EmptyFactory,
    Factory,
    GroupFactory,
    ObjectHeaderFactory,
    PrimitiveFactory,
    STLMapFactory,
    STLSeqFactory,
    STLStringFactory,
    TArrayFactory,
    TObjectFactory,
    TStringFactory,
    build_factory,
    registered_factories,
)
from uproot_custom.utils import regularize_object_path

# register interpretations
uproot.register_interpretation(AsCustom)
