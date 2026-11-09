"""
Run a detree reader tree in Python, without the virtual machine.

The reader's `read` / `read_many` / `read_until` / `read_many_memberwise`
are ordinary Python methods; `uproot_custom.detree.compiler.frontend` only
*compiles* them so the machine can execute them faster.  This module runs them
directly, through `uproot_custom.detree.stream.Stream`, which implements
the same operations as the machine's opcodes.

Two uses:

* debugging a reader -- `print`, `pdb` and a Python traceback all work;
* a second opinion on the machine and on the compiler -- the three executors
  (`uproot_custom.python`, this one, and the VM) must agree on every basket.

State needs no write-back here: the reader's own attributes *are* the state.
"""

from __future__ import annotations

import numpy as np

from uproot_custom.detree.decl import Reader
from uproot_custom.detree.stream import Stream


def read_basket(
    reader: Reader,
    data: np.ndarray[np.uint8],
    offsets: np.ndarray,
    cursor_offset=0,
    nbyte=None,
):
    """
    Run *reader*'s methods over one basket; return the reader.

    The reader is `uproot_custom.detree.decl.Reader.reset` first, so one
    tree reads one basket after another and the arrays an earlier call returned
    keep their values.

    The cursor runs on across events, exactly as it does in the machine and in
    `uproot_custom.python.read_data`, and each event must end on its
    own entry offset.

    Args:
        reader: the detree reader tree to run.
        data: the basket bytes.
        offsets: the entry offsets, or `None` to derive them from *nbyte*.
        cursor_offset: the basket's `fKeylen`, which is what uproot passes to
            a backend.  An object reference is keyed by its position within the
            file (`pos + fKeylen + kMapOffset`), so a pointer member reads
            the wrong bytes when this is 0 -- silently, without an error.
        nbyte: the fixed entry size, used when *offsets* is `None`.

    Returns:
        The reader, holding the buffers and states of the basket just read.
    """
    reader.reset()
    if offsets is None:
        if nbyte is None:
            raise ValueError("nbyte must be specified if offsets is None")
        if isinstance(data, (bytes, bytearray, memoryview)):
            size = len(data)
        else:
            size = np.asarray(data).size
        offsets = np.arange(size // nbyte + 1, dtype=np.int64) * nbyte
    offsets = np.asarray(offsets, dtype=np.int64)

    stream = Stream(data, offsets, cursor_offset)
    for event in range(stream.entries):
        reader.read(stream)
        expected = int(offsets[event + 1])
        if stream.cursor != expected:
            raise AssertionError(
                f"event {event}: read {stream.cursor - int(offsets[event])} bytes, "
                f"the entry holds {expected - int(offsets[event])}"
            )
    return reader


def read_data(
    reader: Reader,
    data: np.ndarray[np.uint8],
    offsets: np.ndarray,
    cursor_offset=0,
    nbyte=None,
):
    """
    Read one basket in Python and return whatever `reader.data()` returns.

    Args:
        reader: the detree reader tree to run.
        data: the basket bytes.
        offsets: the entry offsets, or `None` to derive them from *nbyte*.
        cursor_offset: the basket's `fKeylen`.
        nbyte: the fixed entry size, used when *offsets* is `None`.

    Returns:
        Whatever `reader.data()` returns.
    """
    return read_basket(reader, data, offsets, cursor_offset, nbyte).data()


__all__ = ["read_basket", "read_data"]
