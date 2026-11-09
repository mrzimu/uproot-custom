"""
The machine seam: backend selection, program caching, and detree execution.
"""

from __future__ import annotations

import struct
import threading

import numpy as np
import pytest

import uproot_custom.detree as dt
from uproot_custom.detree.builtin import PrimitiveReader
from uproot_custom.detree.compiler.frontend import compile_reader
from uproot_custom.detree.run import (
    Compiled,
    backend_name,
    entry_offsets,
    new_machine,
    run,
)

try:
    import detree
except ImportError:  # pragma: no cover - optional dependency
    detree = None

pytestmark = pytest.mark.skipif(detree is None, reason="detree-vm is not installed")


def _available(name):
    from detree.backends import registry

    return any(
        backend == name and level >= 3 and reason is None
        for backend, level, reason in registry.available()
    )


@pytest.fixture
def fresh_backend(monkeypatch):
    """
    Clear the cached selection so a test can seed it from the environment.
    """
    monkeypatch.setattr(dt, "_backend", None)
    monkeypatch.delenv(dt.IMPL_ENV, raising=False)


def test_backend_name_is_the_package_selection(fresh_backend):
    assert dt.get_impl() == "rust"
    assert backend_name() == "rust"

    dt.set_impl("python")
    assert backend_name() == "python"

    with dt.use_impl("cpp"):
        assert backend_name() == "cpp"
    assert backend_name() == "python"


def test_get_backend_reads_the_environment_variable(fresh_backend, monkeypatch):
    monkeypatch.setenv(dt.IMPL_ENV, "python")
    assert dt.get_impl() == "python"


def test_the_backend_refuses_an_unknown_value(fresh_backend, monkeypatch):
    monkeypatch.setenv(dt.IMPL_ENV, "jit")
    with pytest.raises(ValueError, match="Invalid backend"):
        dt.get_impl()

    with pytest.raises(ValueError, match="Invalid backend"):
        dt.set_impl("jit")


def _compiled(reader):
    raw, _ = compile_reader(reader)
    return Compiled(data=raw)


def test_a_compiled_reader_holds_detree_bytes_and_a_module():
    compiled = _compiled(PrimitiveReader("p", typecode="i"))

    assert compiled.data[:4] == b"DETR"
    assert compiled.module.funcs[compiled.module.entry].name == "root.read"


def test_every_basket_gets_a_machine_of_its_own():
    compiled = _compiled(PrimitiveReader("p", typecode="i"))

    assert new_machine(compiled) is not new_machine(compiled)


def test_one_thread_reuses_its_machine_and_another_thread_gets_its_own():
    compiled = _compiled(PrimitiveReader("p", typecode="i"))

    assert compiled.machine() is compiled.machine()

    seen = []

    def build():
        seen.append(compiled.machine())

    worker = threading.Thread(target=build)
    worker.start()
    worker.join()

    assert seen[0] is not compiled.machine()


def test_one_compiled_reader_serves_basket_after_basket():
    compiled = _compiled(PrimitiveReader("p", typecode="i"))

    first, _ = run(compiled, struct.pack(">i", 1), [0, 4])
    second, _ = run(compiled, struct.pack(">i", 2), [0, 4])

    np.testing.assert_array_equal(first["root:values"], [1])
    np.testing.assert_array_equal(second["root:values"], [2])


def test_entry_offsets_derive_fixed_width_offsets():
    offsets = entry_offsets(b"\x00" * 12, None, nbyte=4)
    np.testing.assert_array_equal(offsets, [0, 4, 8, 12])

    with pytest.raises(ValueError, match="nbyte"):
        entry_offsets(b"", None)


@pytest.mark.skipif(not _available("cpp"), reason="the detree C++ machine is not built")
def test_both_machines_produce_the_same_buffers():
    reader = PrimitiveReader("p", typecode="i")
    payload = struct.pack(">iii", 1, -2, 3)
    offsets = np.array([0, 4, 8, 12], dtype=np.int64)

    with dt.use_impl("python"):
        python_buffers, python_states = run(_compiled(reader), payload, offsets)

    with dt.use_impl("cpp"):
        cpp_buffers, cpp_states = run(_compiled(reader), payload, offsets)

    assert python_buffers.keys() == cpp_buffers.keys()
    for name, values in python_buffers.items():
        np.testing.assert_array_equal(values, cpp_buffers[name])
    assert python_states == cpp_states


def test_new_machine_is_a_detree_machine():
    compiled = _compiled(PrimitiveReader("p", typecode="i"))

    machine = new_machine(compiled)

    assert machine.backend == backend_name()
    assert machine.isa == (detree.spec.isa.ISA_MAJOR, detree.spec.isa.ISA_MINOR)
