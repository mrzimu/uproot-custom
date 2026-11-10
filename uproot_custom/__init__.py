from __future__ import annotations

from collections.abc import Iterable

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
from uproot_custom.utils import _regularized_paths, regularize_object_path

uproot.register_interpretation(AsCustom)


def claim(path: str | Iterable[str]) -> None:
    """
    Claim branches for Uproot-custom to interpret.

    A claimed branch is read by `AsCustom` instead of by Uproot's own
    interpretations.  Each path is an object-path in the form
    `branch.object_path` reports it; the paths are regularized here, so the
    trailing `;N` cycle number may be kept or dropped.

    Claim every branch before its interpretation is first computed.  Uproot
    caches that per branch object, so a claim made after `branch.array()`,
    `tree.arrays()` or `tree.show()` has no effect on that file object.

    Args:
        path: one object-path, or an iterable of them.
    """
    AsCustom.target_branches.update(_regularized_paths(path, "claim"))


def release(path: str | Iterable[str]) -> None:
    """
    Withdraw branches claimed with `claim`.

    Releasing a path that was never claimed does nothing.

    Args:
        path: one object-path, or an iterable of them.
    """
    for cur in _regularized_paths(path, "release"):
        AsCustom.target_branches.discard(cur)


def clear_claims() -> None:
    """
    Withdraw every branch claimed with `claim`.
    """
    AsCustom.target_branches.clear()


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
    "claim",
    "clear_claims",
    "get_backend",
    "registered_factories",
    "regularize_object_path",
    "release",
    "set_backend",
    "use_backend",
]
