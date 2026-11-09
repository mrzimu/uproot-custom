"""
What compiling produces, and the one seam that runs it.

The frontend compiles a reader tree to detree-vm IR and `detree.compile`
turns it into canonical module bytes.  A `Compiled` keeps those bytes,
the decoded module, and one `detree.Machine` per backend and thread;
the reader and the machine hold the only mutable per-basket state.

A machine is not thread-safe and detree-vm does not hand out a shared wrapper,
so this module owns the per-thread machine cache.  `detree.Machine.run` resets
the machine first, which is what lets one machine serve basket after basket.
"""

from __future__ import annotations

import functools
import threading
from dataclasses import dataclass, field

import numpy as np

from uproot_custom.detree.cache import get as _cache_get
from uproot_custom.detree.cache import put as _cache_put
from uproot_custom.detree.compiler.frontend import (
    _buffer_items,
    _reader_children,
    compile_reader,
    describe_reader,
)
from uproot_custom.detree.decl import Reader, State

_core_module = None
_core_checked = False


def core():
    """
    detree-vm when it has a compiled backend, or `None`.

    The Python reference machine is always available; this probe is only used to
    decide whether a compiled machine can be exercised in tests and benchmarks.
    """
    global _core_module, _core_checked
    if not _core_checked:
        _core_checked = True
        try:
            import detree
            from detree.backends import registry
        except ImportError:  # pragma: no cover - detree-vm is a test dependency
            _core_module = None
        else:
            _core_module = (
                detree
                if any(
                    name in ("cpp", "rust") and level >= 3 and reason is None
                    for name, level, reason in registry.available()
                )
                else None
            )
    return _core_module


def backend_name():
    """
    Which detree-vm machine `new_machine` and `run` select.

    The choice is `uproot_custom.detree.get_impl`, so `set_impl` and
    `use_impl` drive it and `UPROOT_CUSTOM_DETREE_BACKEND` seeds it.  The
    import is deferred because the package's `__init__` imports this module
    while it loads.
    """
    from uproot_custom.detree import get_impl

    return get_impl()


@dataclass(frozen=True)
class Compiled:
    """
    A compiled reader: detree-vm bytes, its module, and per-thread machines.

    `data` is the canonical module a machine in this process (or another
    language) takes.  `module` is decoded and validated once, so callers can
    inspect the artefact without decoding the bytes again.

    `detree.Machine` is not thread-safe, so the cache lives in a
    `threading.local`: two threads running the same `Compiled` get two
    machines, and a thread that switches backends gets one machine per backend.
    """

    data: bytes
    module: object = field(default=None, repr=False, compare=False)
    _machines: threading.local = field(
        default_factory=threading.local, repr=False, compare=False
    )

    def __post_init__(self):
        if self.module is None:
            from detree.spec.module import Module
            from detree.spec.validate import validate_module

            module = Module.from_bytes(self.data)
            validate_module(module)
            object.__setattr__(self, "module", module)

    def machine(self, backend=None):
        """
        The machine this thread uses for *backend*, built on first use.

        The backend defaults to `backend_name()`, and a thread that switches
        backends keeps its earlier machine, so outputs it still holds stay
        readable.
        """
        name = backend_name() if backend is None else backend
        machines = getattr(self._machines, "by_backend", None)
        if machines is None:
            machines = {}
            self._machines.by_backend = machines
        machine = machines.get(name)
        if machine is None:
            import detree

            machine = detree.Machine(self.data, backend=name)
            machines[name] = machine
        return machine


def new_machine(compiled: Compiled):
    """
    A fresh detree-vm machine for *compiled*, built for one call.

    This is the one-shot form, useful for tests and for callers that do not
    want a thread-local machine.  The read path uses `Compiled.machine`,
    which caches one machine per thread and backend and resets it before every
    basket.

    Which implementation this returns is `backend_name`'s decision; all
    backends start from a clean state, so the caller cannot tell them apart.
    """
    import detree

    return detree.Machine(compiled.data, backend=backend_name())


def _as_uint8(data):
    """
    The basket's bytes as a C-contiguous uint8 array (no copy when possible).
    """
    if isinstance(data, np.ndarray):
        if data.dtype == np.uint8 and data.flags["C_CONTIGUOUS"]:
            return data
        return np.ascontiguousarray(data, dtype=np.uint8)
    return np.frombuffer(data, dtype=np.uint8)


def run(
    compiled: Compiled,
    data: bytes,
    offsets: np.ndarray,
    cursor_offset: int = 0,
    nbyte: int | None = None,
):
    """
    Run *compiled* over one basket; return `(buffers, states)`.

    `buffers` is `{declared name: 1-D array}` and `states` is
    `{declared name: int | str | None}` (a name slot comes back decoded from
    the string arena, `None` when it is empty).

    The machine is this thread's cached one (`Compiled.machine`), and
    `detree.Machine.run` resets it before reading, so two threads may run the
    same `Compiled` at the same time without sharing registers or buffers.

    Args:
        compiled: the compiled reader to run.
        data: the basket bytes.
        offsets: the entry offsets, or `None` to derive them from *nbyte*.
        cursor_offset: the basket's `fKeylen`.
        nbyte: the fixed entry size, used when *offsets* is `None`; a
            fixed-width branch is then `i * nbyte` per event.

    Returns:
        `(buffers, states)` as described above.
    """
    offsets = entry_offsets(data, offsets, nbyte)
    machine = compiled.machine()
    outputs = machine.run(_as_uint8(data), offsets, cursor_offset)
    return outputs, machine.state_values()


def compiled_for_reader(reader: Reader) -> Compiled:
    """
    Return the cached compilation of a reader tree, compiling it on first use.
    """
    signature = "ast:" + describe_reader(reader)
    compiled = _cache_get(signature)
    if compiled is None:
        raw, _ = compile_reader(reader)
        compiled = Compiled(data=raw)
        _cache_put(signature, compiled)
    return compiled


@functools.lru_cache(maxsize=64)
def _fixed_offsets(count: int, nbyte: int) -> np.ndarray:
    """
    `i * nbyte` for every entry; cached because every full basket matches.
    """
    offsets = np.arange(count, dtype=np.int64) * nbyte
    offsets.flags.writeable = False
    return offsets


def entry_offsets(data, offsets, nbyte=None):
    """
    The entry offsets of a basket, derived from *nbyte* when absent.

    A fixed-width branch has no `byte_offsets`; every entry is then the same
    size and the offsets are just `i * nbyte`. Every basket of a branch but
    the last has the same length, so the array is built once per length.
    """
    if offsets is not None:
        return offsets
    if nbyte is None:
        raise ValueError("nbyte must be specified if offsets is None")
    if isinstance(data, (bytes, bytearray, memoryview)):
        size = len(data)
    else:
        size = np.asarray(data).size
    return _fixed_offsets(size // nbyte + 1, nbyte)


def apply_outputs(reader: Reader, outputs: dict, states=None, path="root"):
    """
    Write the buffers the machine filled back into the reader and its children.

    A native buffer adopts the array without copying.  *states* is the
    `{name: value}` mapping the machine returns; when given, the Python side
    of a reader ends up with the values the run ended with.
    """
    for attr, _, _ in _buffer_items(reader):
        getattr(reader, attr).adopt(outputs[f"{path}:{attr}"])
    if states is not None:
        for field in reader.__fields__:
            if isinstance(field, State):
                setattr(reader, field.name, states[f"{path}:{field.name}"])
    for _, child, suffix in _reader_children(reader):
        apply_outputs(child, outputs, states, path + suffix)


def read_data(
    reader: Reader,
    data: bytes,
    offsets: np.ndarray,
    cursor_offset: int = 0,
    nbyte: int | None = None,
):
    """
    Read one basket: compile *reader*, run it, hand the buffers back.

    *cursor_offset* is the basket's `fKeylen`, as uproot passes it; an object
    reference is keyed by its position within the file, so a pointer member
    reads the wrong bytes when this is 0.

    The reader is reset first, exactly as `uproot_custom.detree.interp` does,
    so one tree reads basket after basket on either executor and the arrays a
    previous call returned stay valid.

    Args:
        reader: the native reader tree to compile and run.
        data: the basket bytes.
        offsets: the entry offsets, or `None` to derive them from *nbyte*.
        cursor_offset: the basket's `fKeylen`.
        nbyte: the fixed entry size, used when *offsets* is `None`.

    Returns:
        Whatever `reader.data()` returns; the caller turns it into an awkward
        array, usually through the factory that built the reader.
    """
    reader.reset()
    outputs, states = run(compiled_for_reader(reader), data, offsets, cursor_offset, nbyte)
    apply_outputs(reader, outputs, states)
    return reader.data()


__all__ = [
    "Compiled",
    "apply_outputs",
    "backend_name",
    "compiled_for_reader",
    "core",
    "entry_offsets",
    "new_machine",
    "read_data",
    "run",
]
