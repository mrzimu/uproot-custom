"""
The machine seam: backend selection, program caching, and detree execution.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

import uproot_custom.detree as dt
from uproot_custom.detree.builtin import PrimitiveReader
from uproot_custom.detree.compiler.frontend import compile_reader
from uproot_custom.detree.run import backend_name, entry_offsets, run

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


def _codes(reader):
    codes, _ = compile_reader(reader)
    return codes


def test_the_compiled_bytes_are_a_detree_module():
    codes = _codes(PrimitiveReader("p", typecode="i"))

    assert codes[:4] == b"DETR"
    module = detree.spec.module.Module.from_bytes(codes)
    detree.spec.validate.validate_module(module)
    assert module.funcs[module.entry].name == "root.read"


def test_every_run_builds_a_machine_of_its_own(monkeypatch):
    built = []
    machine_class = detree.Machine

    def factory(code, backend=None):
        machine = machine_class(code, backend=backend)
        built.append(machine)
        return machine

    monkeypatch.setattr(detree, "Machine", factory)
    codes = _codes(PrimitiveReader("p", typecode="i"))

    run(codes, struct.pack(">i", 1), [0, 4])
    run(codes, struct.pack(">i", 2), [0, 4])

    assert len(built) == 2
    assert built[0] is not built[1]


def test_one_module_serves_basket_after_basket():
    codes = _codes(PrimitiveReader("p", typecode="i"))

    first, _ = run(codes, struct.pack(">i", 1), [0, 4])
    second, _ = run(codes, struct.pack(">i", 2), [0, 4])

    np.testing.assert_array_equal(first["root:values"], [1])
    np.testing.assert_array_equal(second["root:values"], [2])


def test_entry_offsets_derive_fixed_width_offsets():
    offsets = entry_offsets(b"\x00" * 12, None, nbyte=4)
    np.testing.assert_array_equal(offsets, [0, 4, 8, 12])

    with pytest.raises(ValueError, match="nbyte"):
        entry_offsets(b"", None)


def test_run_derives_fixed_width_offsets_from_nbyte():
    codes = _codes(PrimitiveReader("p", typecode="i"))

    outputs, _ = run(codes, struct.pack(">ii", 1, 2), None, nbyte=4)

    np.testing.assert_array_equal(outputs["root:values"], [1, 2])


@pytest.mark.skipif(not _available("cpp"), reason="the detree C++ machine is not built")
def test_both_machines_produce_the_same_buffers():
    codes = _codes(PrimitiveReader("p", typecode="i"))
    payload = struct.pack(">iii", 1, -2, 3)
    offsets = np.array([0, 4, 8, 12], dtype=np.int64)

    with dt.use_impl("python"):
        python_buffers, python_states = run(codes, payload, offsets)

    with dt.use_impl("cpp"):
        cpp_buffers, cpp_states = run(codes, payload, offsets)

    assert python_buffers.keys() == cpp_buffers.keys()
    for name, values in python_buffers.items():
        np.testing.assert_array_equal(values, cpp_buffers[name])
    assert python_states == cpp_states


def test_run_selects_the_configured_machine(monkeypatch):
    seen = []
    machine_class = detree.Machine

    def factory(code, backend=None):
        seen.append(backend)
        return machine_class(code, backend=backend)

    monkeypatch.setattr(detree, "Machine", factory)
    codes = _codes(PrimitiveReader("p", typecode="i"))

    with dt.use_impl("python"):
        run(codes, struct.pack(">i", 1), [0, 4])

    assert seen == ["python"]
