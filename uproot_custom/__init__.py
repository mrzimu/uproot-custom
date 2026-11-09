from __future__ import annotations

import uproot

from uproot_custom.backend import get_backend, set_backend, use_backend
from uproot_custom.factories import (
    AnyClassFactory,
    AnyPointerFactory,
    BaseObjectFactory,
    CStyleArrayFactory,
    EmptyFactory,
    Factory,
    GroupFactory,
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
from uproot_custom.interpretation import AsCustom
from uproot_custom.utils import regularize_object_path

uproot.register_interpretation(AsCustom)


__all__ = [
    "AnyClassFactory",
    "AnyPointerFactory",
    "AsCustom",
    "BaseObjectFactory",
    "CStyleArrayFactory",
    "EmptyFactory",
    "Factory",
    "GroupFactory",
    "PrimitiveFactory",
    "STLMapFactory",
    "STLSeqFactory",
    "STLStringFactory",
    "TArrayFactory",
    "TObjectFactory",
    "TStringFactory",
    "build_factory",
    "get_backend",
    "registered_factories",
    "regularize_object_path",
    "set_backend",
    "use_backend",
]
