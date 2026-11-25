"""
The compiled module on disk: what makes a hit, and what keeps a hit safe.

`test_pipeline.py` walks the pipeline stage by stage; this file is about the
file level under `__pycache__/detree/`, which `AsCustom` reaches through the
same `compiled_for_reader`.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import awkward as ak
import pytest
import uproot

import uproot_custom
from uproot_custom.detree import builtin, cache
from uproot_custom.detree import run as detree_run
from uproot_custom.detree.compiler.frontend import compile_reader, describe_reader

DATA = Path(__file__).parent.parent / "data"


@pytest.fixture(autouse=True)
def empty_cache():
    """
    Start and end every test with no compiled module in the process.
    """
    cache.clear()
    cache.reset()
    yield
    cache.clear()
    cache.reset()


def _reader(typecode="i"):
    """
    A tree of two classes, so the key has to cover more than the root.
    """
    return builtin.STLSeqReader(
        "v", with_header=True, element=builtin.PrimitiveReader("e", typecode=typecode)
    )


def _entries():
    """
    The entry files of the cache directory.
    """
    root = cache.directory()
    assert root is not None
    return sorted(root.glob("*.mod"))


def test_a_second_process_reads_the_module_instead_of_compiling(monkeypatch):
    """
    Emptying the in-process dict must not bring the compiler back.
    """
    first = detree_run.compiled_for_reader(_reader())
    assert first[:4] == b"DETR"
    cache.clear()

    def explode(reader):
        raise AssertionError("the compiler ran although an entry was on disk")

    monkeypatch.setattr(detree_run, "compile_reader", explode)

    before = cache.STATS["disk_hits"]
    writes = cache.STATS["writes"]
    assert detree_run.compiled_for_reader(_reader()) == first
    assert cache.STATS["disk_hits"] == before + 1
    assert cache.STATS["writes"] == writes


def test_two_threads_sharing_a_tree_write_one_entry():
    """
    The compile-and-store path is not serialized, so both threads may compile;
    what has to hold is that they agree and leave one entry behind.
    """
    with ThreadPoolExecutor(max_workers=4) as pool:
        modules = list(pool.map(lambda _: detree_run.compiled_for_reader(_reader()), range(8)))

    assert len(set(modules)) == 1
    assert len(_entries()) == 1


def test_an_entry_is_byte_identical_to_a_fresh_compile():
    """
    A hit and a compile have to be indistinguishable, or a cache changes reads.
    """
    reader = _reader()
    compiled, _ = compile_reader(reader)

    detree_run.compiled_for_reader(reader)
    cache.clear()

    assert detree_run.compiled_for_reader(_reader()) == compiled


def test_a_broken_entry_is_deleted_and_recompiled():
    """
    A truncated file costs one compile, and the next read finds a good entry.
    """
    codes = detree_run.compiled_for_reader(_reader())
    (entry,) = _entries()
    entry.write_bytes(b"DETR")

    cache.clear()
    before = cache.STATS["read_errors"]

    assert detree_run.compiled_for_reader(_reader()) == codes
    assert cache.STATS["read_errors"] == before + 1
    assert entry.read_bytes() == codes


def test_a_directory_that_cannot_be_created_does_not_break_the_read(tmp_path, monkeypatch):
    """
    A read-only install keeps working; only the disk level is lost.
    """
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setattr(cache, "DISK_ROOT", blocker / "detree")

    before = cache.STATS["write_errors"]
    codes = detree_run.compiled_for_reader(_reader())

    assert codes[:4] == b"DETR"
    assert cache.STATS["write_errors"] == before + 1


def test_the_disk_level_can_be_switched_off(monkeypatch):
    """
    `$UPROOT_CUSTOM_DETREE_CACHE=0` leaves the compiler as the only source.
    """
    monkeypatch.setattr(cache, "DISK_ROOT", None)
    monkeypatch.delenv(cache.DIRECTORY_ENV, raising=False)
    monkeypatch.setenv(cache.DISABLE_ENV, "0")

    assert cache.directory() is None
    assert cache.load("0" * 64) is None
    assert not cache.store("0" * 64, b"DETR")


def test_a_key_that_is_not_a_digest_is_refused():
    """
    A malformed key would name a file that no entry name matches, which nothing
    could ever prune, so both ends refuse it instead of writing it.
    """
    with pytest.raises(ValueError):
        cache.load("not-a-digest")
    with pytest.raises(ValueError):
        cache.store("not-a-digest", b"DETR")
    assert _entries() == []


def test_the_environment_variable_chooses_the_directory(tmp_path, monkeypatch):
    """
    A shared directory is how several environments reuse one set of entries.
    """
    monkeypatch.setattr(cache, "DISK_ROOT", None)
    monkeypatch.delenv(cache.DISABLE_ENV, raising=False)
    target = tmp_path / "elsewhere"
    monkeypatch.setenv(cache.DIRECTORY_ENV, str(target))

    detree_run.compiled_for_reader(_reader())

    assert target.is_dir()
    assert len(list(target.glob("*.mod"))) == 1


def test_the_default_directory_follows_the_bytecode_cache(tmp_path, monkeypatch):
    """
    With no override the entries sit beside the package, and `sys.pycache_prefix`
    moves them the way it moves `.pyc` files.
    """
    monkeypatch.setattr(cache, "DISK_ROOT", None)
    monkeypatch.delenv(cache.DIRECTORY_ENV, raising=False)
    monkeypatch.delenv(cache.DISABLE_ENV, raising=False)
    monkeypatch.setattr(sys, "pycache_prefix", None)

    default = cache.directory()
    assert default is not None
    assert default.name == "detree"
    assert default.parent.name == "__pycache__"

    monkeypatch.setattr(sys, "pycache_prefix", str(tmp_path))
    moved = cache.directory()
    assert moved is not None
    assert moved.name == "detree"
    assert tmp_path in moved.parents


def test_one_entry_serves_every_reader_of_one_shape():
    """
    Entries are per reader structure, not per branch: the name is not compiled.
    """
    detree_run.compiled_for_reader(builtin.PrimitiveReader("a", typecode="i"))
    detree_run.compiled_for_reader(builtin.PrimitiveReader("b", typecode="i"))
    assert len(_entries()) == 1

    detree_run.compiled_for_reader(builtin.PrimitiveReader("c", typecode="d"))
    assert len(_entries()) == 2


def test_an_entry_from_another_generation_is_pruned_on_the_next_write():
    """
    A stale generation is dead weight: nothing can read it, so a write drops it.
    """
    root = cache.directory()
    root.mkdir(parents=True)
    stale = root / ("deadbeef-" + "0" * 64 + ".mod")
    stale.write_bytes(b"DETR")

    detree_run.compiled_for_reader(_reader())

    assert not stale.exists()
    assert len(_entries()) == 1


def test_an_entry_of_another_generation_is_never_read():
    """
    Pruning is hygiene; the correctness rule is the generation in the name.

    The file below holds a valid module, compiled from another tree and stored
    under this tree's key, so a reader that ignored the generation would get
    plausible bytes for the wrong shape rather than an obvious error.
    """
    reader = _reader()
    signature = "ast:" + describe_reader(reader)
    key = cache.key_for(signature, reader)
    codes, _ = compile_reader(reader)
    other, _ = compile_reader(builtin.PrimitiveReader("x", typecode="d"))

    root = cache.directory()
    root.mkdir(parents=True)
    stale = root / ("0000dead-" + key + ".mod")
    stale.write_bytes(other)

    hits, errors = cache.STATS["disk_hits"], cache.STATS["read_errors"]
    assert detree_run.compiled_for_reader(reader) == codes

    assert cache.STATS["disk_hits"] == hits
    assert cache.STATS["read_errors"] == errors
    assert not stale.exists()


def test_prune_keeps_the_entries_of_the_current_generation():
    """
    `prune` deletes by generation, not by directory: this generation stays.

    `reset` forgets that this process already pruned, so the second store runs
    `prune` with a current-generation entry already in place.
    """
    detree_run.compiled_for_reader(builtin.PrimitiveReader("a", typecode="i"))
    assert len(_entries()) == 1

    cache.reset()
    detree_run.compiled_for_reader(builtin.PrimitiveReader("b", typecode="d"))

    assert len(_entries()) == 2


def test_prune_leaves_a_temporary_file_alone():
    """
    Another process may be writing that file; only entry names are pruned.
    """
    root = cache.directory()
    root.mkdir(parents=True)
    partial = root / ".tmp-1234abcd.mod"
    partial.write_bytes(b"DETR")

    detree_run.compiled_for_reader(_reader())

    assert partial.exists()


def test_prune_removes_an_abandoned_temporary_file():
    """
    A writer that died mid-way leaves a file no other step would ever remove.
    """
    root = cache.directory()
    root.mkdir(parents=True)
    abandoned = root / ".tmp-deadbeef.mod"
    abandoned.write_bytes(b"DETR")
    old = time.time() - 2 * cache._TEMPORARY_AGE
    os.utime(abandoned, (old, old))

    detree_run.compiled_for_reader(_reader())

    assert not abandoned.exists()


def test_a_new_generation_replaces_the_old_entry(monkeypatch):
    """
    A real generation change writes a new file and takes the old one away.
    """
    detree_run.compiled_for_reader(_reader())
    first = {entry.name for entry in _entries()}
    assert len(first) == 1

    cache.clear()
    cache.reset()
    monkeypatch.setenv("DETREE_OPT", "0")
    detree_run.compiled_for_reader(_reader())

    second = _entries()
    assert len(second) == 1
    assert second[0].name not in first


def test_clear_disk_deletes_the_entries():
    """
    The documented way to start over, without hunting for the directory.
    """
    detree_run.compiled_for_reader(_reader())
    assert len(_entries()) == 1

    cache.clear_disk()

    assert _entries() == []


def test_a_disabled_bytecode_cache_keeps_the_module_in_memory(monkeypatch):
    """
    `python -B` asks for no cache files, and that has to cover this one too.
    """
    monkeypatch.setattr(sys, "dont_write_bytecode", True)

    before = cache.STATS["writes"]
    detree_run.compiled_for_reader(_reader())

    assert _entries() == []
    assert cache.STATS["writes"] == before


def test_the_key_covers_the_source_of_the_reader(monkeypatch):
    """
    A signature names a class, not a method body, so the source is hashed too.
    """
    reader = _reader()
    signature = "ast:" + describe_reader(reader)
    before = cache.key_for(signature, reader)

    digest = cache._file_digest
    monkeypatch.setattr(
        cache,
        "_file_digest",
        lambda path: "edited" if str(path).endswith("builtin.py") else digest(path),
    )

    assert cache.key_for(signature, reader) != before


def test_the_key_covers_a_base_class_in_another_module(tmp_path, monkeypatch):
    """
    A reader may inherit `read`, and the frontend compiles `inspect.getsource`
    of the method, which resolves to the class that defines it.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    base = tmp_path / "cache_test_base.py"
    base.write_text(
        "from uproot_custom.detree.builtin import PrimitiveReader\n"
        "\n"
        "\n"
        "class BaseReader(PrimitiveReader):\n"
        "    def read(self, stream):\n"
        "        self.value.read(stream)\n"
    )
    (tmp_path / "cache_test_sub.py").write_text(
        "from cache_test_base import BaseReader\n"
        "\n"
        "\n"
        "class SubReader(BaseReader):\n"
        "    pass\n"
    )
    reader = importlib.import_module("cache_test_sub").SubReader("x", typecode="i")
    signature = "ast:" + describe_reader(reader)

    assert str(base) in cache._reader_sources(reader)
    before = cache.key_for(signature, reader)

    base.write_text(base.read_text() + "# an edit that changes no behaviour\n")

    assert cache.key_for(signature, reader) != before


def test_the_generation_follows_an_editable_detree(monkeypatch):
    """
    A released Detree is identified by its version; an editable one keeps that
    version while its source changes, so the source has to enter the generation.
    """
    monkeypatch.setattr(cache, "_editable", lambda distribution: False)
    cache.reset()
    released = cache.generation()

    monkeypatch.setattr(cache, "_editable", lambda distribution: True)
    cache.reset()

    assert cache.generation() != released


def test_the_generation_follows_the_optimizer_switch(monkeypatch):
    """
    `DETREE_OPT=0` produces other bytes, so it must produce another key space.
    """
    monkeypatch.delenv("DETREE_OPT", raising=False)
    cache.reset()
    optimized = cache.generation()

    monkeypatch.setenv("DETREE_OPT", "0")
    cache.reset()

    assert cache.generation() != optimized


def test_a_branch_read_uses_the_entry_left_by_an_earlier_process(monkeypatch):
    """
    The whole path, through `AsCustom.basket_array`, with the compiler refused.
    """
    path = DATA / "test_primitive.root"
    branch = "/tree:branch/m_int"

    with uproot_custom.use_backend("detree"), uproot.open(path) as file:
        expected = file[branch].array(library="ak")

    cache.clear()

    def explode(reader):
        raise AssertionError("the compiler ran although an entry was on disk")

    monkeypatch.setattr(detree_run, "compile_reader", explode)

    with uproot_custom.use_backend("detree"), uproot.open(path) as file:
        actual = file[branch].array(library="ak")

    assert ak.almost_equal(expected, actual)
