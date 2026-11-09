"""
The detree backend, exercised stage by stage.

The fixture-wide comparison with the Python backend lives in
`tests/test_readers.py`; this file walks the pipeline itself so a break is
attributed to the stage that produced it: the awkward form, the compiled
module, the refusal of a factory without a native reader, the per-branch
compilation cache, and concurrent reads of one branch.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import awkward as ak
import detree
import pytest
import uproot

from uproot_custom import AsCustom
from uproot_custom.backend import use_backend
from uproot_custom.detree import cache
from uproot_custom.detree.compiler.frontend import compile_reader, describe_reader
from uproot_custom.detree.run import compiled_for_reader
from uproot_custom.factories import Factory

DATA = Path(__file__).parent.parent / "data"


def read_branch(path, branch, **kwargs):
    """
    Open a fresh file under the detree backend and read *branch*.
    """
    with use_backend("detree"), uproot.open(path) as file:
        return file[branch].array(**kwargs)


def test_the_awkward_form_matches_the_python_backend():
    path = DATA / "test_stl_sequence.root"
    branch = "/tree:branch/m_vec_double"

    with use_backend("detree"), uproot.open(path) as file:
        entry = file[branch]
        detree_form = entry.interpretation.awkward_form(entry.file)

    with use_backend("python"), uproot.open(path) as file:
        entry = file[branch]
        python_form = entry.interpretation.awkward_form(entry.file)

    assert detree_form == python_form


def test_the_stages_are_wired():
    path = DATA / "test_stl_sequence.root"
    branch = "/tree:branch/m_vec_double"

    with use_backend("detree"), uproot.open(path) as file:
        interpretation = file[branch].interpretation
        assert isinstance(interpretation, AsCustom)

        factory = interpretation.factory
        assert type(factory).__name__ == "STLSeqFactory"

        reader = factory.build_detree_reader()
        raw, signature = compile_reader(reader)
        assert signature == describe_reader(reader)

        module = detree.spec.module.Module.from_bytes(raw)
        detree.spec.validate.validate_module(module)
        assert [decl.name for decl in module.buffers] == [
            "root:offsets",
            "root/element:values",
        ]
        assert [decl.kind for decl in module.buffers] == [
            detree.spec.isa.BufferKind.OFFSETS,
            detree.spec.isa.BufferKind.DATA,
        ]

        compiled = compiled_for_reader(reader)
        assert compiled.data == raw
        assert compiled.data[:4] == b"DETR"
        assert compiled.module.funcs[compiled.module.entry].name == "root.read"

        hits = cache.STATS["hits"]
        assert compiled_for_reader(reader) is compiled
        assert cache.STATS["hits"] == hits + 1


def test_a_factory_without_a_native_reader_is_refused():
    with pytest.raises(NotImplementedError, match="does not build a native reader"):
        Factory("stub").build_detree_reader()


def test_a_branch_without_a_native_reader_is_refused():
    path = DATA / "test_primitive.root"
    branch = "/tree:branch/m_int"

    with use_backend("detree"), uproot.open(path) as file:
        entry = file[branch]
        interpretation = entry.interpretation
        interpretation._factory = Factory("stub")

        basket = entry.basket(0)
        library = uproot.interpretation.library.Awkward()
        with pytest.raises(NotImplementedError, match="does not build a native reader"):
            interpretation.basket_array(
                basket.data,
                basket.byte_offsets,
                basket,
                entry,
                dict(entry.context),
                basket.member("fKeylen"),
                library,
                {},
            )


def test_the_compiled_reader_is_cached_on_the_branch():
    """
    Compiling is per branch, not per basket: the artefact is reused as is.
    """
    path = DATA / "test_stl_sequence.root"
    branch = "/tree:branch/m_vec_double"

    with use_backend("detree"), uproot.open(path) as file:
        entry = file[branch]
        entry.array(library="ak")
        compiled = entry.interpretation._compiled_detree_reader

        entry.file._array_cache = None
        entry.array(library="ak")

    assert entry.interpretation._compiled_detree_reader is compiled


def test_switching_backends_returns_the_same_array():
    path = DATA / "test_stl_sequence.root"
    branch = "/tree:branch/m_vec_double"

    with use_backend("python"), uproot.open(path) as file:
        expected = file[branch].array()

    actual = read_branch(path, branch)

    assert ak.array_equal(expected, actual)


def test_concurrent_reads_of_one_branch_do_not_share_state():
    """
    Every basket owns its reader and its machine, so threads cannot collide.

    this runs the same basket through the same interpretation on eight threads
    and demands that every answer equal the first.
    """
    path = DATA / "test_stl_sequence.root"
    branch = "/tree:branch/m_vec_double"

    with use_backend("detree"), uproot.open(path) as file:
        entry = file[branch]
        interpretation = entry.interpretation
        assert isinstance(interpretation, AsCustom)

        assert entry.num_baskets > 0
        basket = entry.basket(0)
        library = uproot.interpretation.library.Awkward()

        def read(_):
            return interpretation.basket_array(
                basket.data,
                basket.byte_offsets,
                basket,
                entry,
                dict(entry.context),
                basket.member("fKeylen"),
                library,
                {},
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(read, range(16)))

    assert len(results) == 16
    for result in results[1:]:
        assert ak.almost_equal(results[0], result)
