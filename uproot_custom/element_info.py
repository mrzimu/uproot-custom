"""
The streamer-info fields the factories read, in one normalized form.

A `TStreamerElement` reaches this package as the ``all_members`` mapping of an
`uproot` model, after two rewrites that must not be mistaken for the file's
own values:

* ROOT recomputes ``fType`` when it reads an info back, so a stored 500 comes
  back as 300 or 320 and a stored 82 stays 82 (`StreamerInfo.md` §10);
* `uproot` subtracts ``kOffsetL`` from the basic codes, so the factory sees 3
  where the file says 23 (`uproot/streamers.py`, ``Model_TStreamerBasicType``).

Neither rewrite touches the codes that decide the framing of a fixed array,
which is why :class:`ElementFrame` is derived here and nowhere else, and why
nothing in this module tries to reconstruct a ``std::array``: the file cannot
tell one from a C array, and a reader does not need to know
(`Collections.md` §11).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ElementFrame", "ElementInfo"]


class ElementFrame(enum.Enum):
    """
    How a run of ``fArrayLength`` elements of one member is framed.

    This describes the *array* form only. A scalar member's own framing is the
    reader's business: a lone ``vector`` is a member and carries a
    ``fNBytes+fVersion`` header, and so does a fixed array of them, but the
    second is one header for the whole run.
    """

    #: No header anywhere: basic types and their C arrays, which are raw values.
    NONE = "none"

    #: Every element frames itself: objects (61/62), their array forms (81/82)
    #: and the pointer codes, which keep their scalar code and record the array
    #: in ``fArrayLength`` instead (`ElementTypes.md` §7.2).
    OBJECT = "object"

    #: One ``fNBytes+fVersion`` header before all ``fArrayLength`` elements:
    #: 85/86/87 and, through `Collections.md` §11.1, a fixed array of collections.
    SHARED = "shared"


#: Scalar codes whose array form wraps the whole run in one header, plus
#: ``kOffsetL``: 65+20, 66+20, 67+20.
_SHARED_HEADER_CODES = frozenset({85, 86, 87})

#: ``TStreamerSTL`` stores 500 whatever the member is; a fixed array of them
#: shares one header too (`Collections.md` §11.1).
_KSTL_CODE = 500

#: Codes that are self-framed per element, including the array forms 81 and 82.
_SELF_FRAMED_CODES = frozenset({61, 62, 63, 64, 68, 69, 81, 82})


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_int_tuple(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    try:
        return tuple(int(x) for x in value)
    except (TypeError, ValueError):
        return ()


@dataclass(frozen=True)
class ElementInfo:
    """
    The streamer-info fields one factory decision needs.

    The fields are documented as ``#:`` comments rather than in an
    ``Attributes:`` block: the API pages document the attributes themselves, and
    a Google ``Attributes:`` section would register every one of them twice.
    """

    #: ``fName``, the member name; for a top-level class it is the class.
    name: str

    #: ``fTypeName``, or ``None`` for a synthetic element.
    type_name: str | None

    #: ``fType`` as `uproot` hands it over, after both rewrites.
    ftype: int | None

    #: ``fArrayLength``, the element count of an array form.
    array_length: int

    #: ``fArrayDim``; 0 means either a scalar or a pre-6.24/02 array.
    array_dim: int

    #: ``fMaxIndex``, the per-dimension extents.
    max_index: tuple[int, ...]

    @classmethod
    def from_streamer_info(cls, streamer_info: Mapping[str, Any]) -> ElementInfo:
        """
        Normalize one ``TStreamerElement.all_members`` mapping.

        Args:
            streamer_info: the mapping `uproot` exposes for one element. Missing
                keys are allowed: the factories build synthetic elements that
                carry nothing but a name and a type name.

        Returns:
            The normalized element.
        """
        return cls(
            name=str(streamer_info.get("fName", "")),
            type_name=streamer_info.get("fTypeName"),
            ftype=_as_int(streamer_info.get("fType")),
            array_length=_as_int(streamer_info.get("fArrayLength")) or 0,
            array_dim=_as_int(streamer_info.get("fArrayDim")) or 0,
            max_index=_as_int_tuple(streamer_info.get("fMaxIndex")),
        )

    @property
    def is_array(self) -> bool:
        """
        Whether the element declares an array form at all.

        ``fArrayDim`` and ``fArrayLength`` are both untouched by the two
        rewrites, so either one decides. ``fArrayLength`` alone is what the
        specification requires a reader to use (`ElementTypes.md` §7.2); a
        scalar records 0 there, and the pointer codes record the count without
        adding ``kOffsetL``.

        The test is ``> 1`` rather than ``> 0`` because a scalar pointer member
        is not documented to record 0: ``ElementTypes.md`` §7.2 only says that an
        array of them has ``fArrayLength > 1``. A single-element array still
        matches through ``fArrayDim``.
        """
        return self.array_dim > 0 or self.array_length > 1

    @property
    def element_count(self) -> int | None:
        """
        The number of elements the array form holds, or ``None`` for a scalar.

        ``fArrayLength`` is the authority (`ElementTypes.md` §7.2). The product
        of ``fMaxIndex`` is only a fallback for an element that predates it or
        that a hand-written info left unset.
        """
        if self.array_length > 0:
            return self.array_length
        if self.array_dim > 0:
            count = 1
            for extent in self.max_index[: self.array_dim]:
                count *= extent
            return count or None
        return None

    @property
    def dims(self) -> tuple[int, ...]:
        """
        The extents to reshape the flat elements into.

        A file written before ROOT 6.24/02 may leave ``fArrayDim`` at 0 while
        ``fArrayLength`` is positive (`StreamerInfo.md` §10); the rank is then
        recovered from the non-zero ``fMaxIndex`` entries. When that also fails,
        the array is one-dimensional, which is what the bytes say anyway.
        """
        if self.array_dim > 0:
            return self.max_index[: self.array_dim]

        count = self.element_count
        if count is None:
            return ()

        extents = tuple(extent for extent in self.max_index if extent > 0)
        if extents and _product(extents) == count:
            return extents
        return (count,)

    @property
    def frame(self) -> ElementFrame:
        """
        Where the header of this element's array form lives, if it has one.
        """
        if self.ftype in _SHARED_HEADER_CODES or self.ftype == _KSTL_CODE:
            return ElementFrame.SHARED
        if self.ftype in _SELF_FRAMED_CODES:
            return ElementFrame.OBJECT
        return ElementFrame.NONE


def _product(values: tuple[int, ...]) -> int:
    res = 1
    for value in values:
        res *= value
    return res
