"""
The compiled-module cache: one dict in the process, one file per module on disk.

`uproot_custom.detree.run.compiled_for_reader` is the only caller.  Inside one
process the module bytes live in `_CACHE`, keyed by the reader's structural
signature.  Across processes they live in one file each under
`__pycache__/detree/`, next to this package, so a second process reads the bytes
instead of running the compiler again.

The disk key cannot be the in-process signature.  A signature names the classes,
their declared constants, buffer dtypes and children, but not the source of the
methods nor the compiler that lowered them, so an edited reader or an upgraded
Detree would keep hitting an entry built from the old code.  `key_for` hashes
the signature together with the source files of every class a reader in the tree
is built from -- bases included, because a method may be inherited -- and a
*generation* digest of everything else that decides what a module looks like,
which includes Detree's own source when Detree is an editable install.  An entry
file is named `<generation>-<key>.mod`, which means an entry from another
generation is never read, and `store` deletes those files the first time it runs
in a process.

The in-process dict is keyed by the signature alone, so it does not notice an
edited source file: the process that already compiled a tree keeps that module
until `clear()` or until the next process.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # a reader appears only in annotations
    from uproot_custom.detree.decl import Reader

_CACHE: dict[str, bytes] = {}

#: `hits` and `misses` count the in-process dict; the rest count the files.
STATS = {
    "hits": 0,
    "misses": 0,
    "disk_hits": 0,
    "writes": 0,
    "read_errors": 0,
    "write_errors": 0,
}

#: Set it to `0` to keep the compiled modules in memory only.
DISABLE_ENV = "UPROOT_CUSTOM_DETREE_CACHE"

#: Set it to a path to replace the cache directory.
DIRECTORY_ENV = "UPROOT_CUSTOM_DETREE_CACHE_DIR"

#: Set it to force a directory; `None` resolves one from the environment.  The
#: test suite points this at a temporary directory, so a run neither writes into
#: the repository nor reads an entry an earlier run left behind.
DISK_ROOT: Path | None = None

_HERE = Path(__file__).resolve().parent

#: what `store` writes, so `prune` and `clear_disk` never touch a temporary file
_ENTRY_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{64}\.mod$")

#: what `load` and `store` accept from a caller
_KEY_NAME = re.compile(r"^[0-9a-f]{64}$")

#: a file `store` is writing, which `prune` only touches once it looks abandoned
_TEMPORARY_NAME = re.compile(r"^\.tmp-.*\.mod$")

#: how long a temporary file may sit before `prune` treats it as abandoned
_TEMPORARY_AGE = 3600

_generation: str | None = None
_source_digests: dict[tuple[str, int, int], str] = {}
_pruned = False


def get(signature: str) -> bytes | None:
    """
    The module already compiled for *signature* in this process, or `None`.
    """
    compiled = _CACHE.get(signature)
    if compiled is None:
        STATS["misses"] += 1
    else:
        STATS["hits"] += 1
    return compiled


def put(signature: str, codes: bytes) -> bytes:
    """
    Keep *codes* in this process, keyed by the reader's signature.
    """
    _CACHE[signature] = codes
    return codes


def size() -> int:
    """
    How many modules this process has compiled or loaded.
    """
    return len(_CACHE)


def clear() -> None:
    """
    Empty the in-process cache; the files on disk are left alone.
    """
    _CACHE.clear()
    STATS["hits"] = 0
    STATS["misses"] = 0


def clear_disk() -> None:
    """
    Delete every entry file in `directory()`.

    A temporary file is left alone; `prune` removes the ones that were abandoned
    by a writer that died.
    """
    root = directory()
    if root is None:
        return
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        if _ENTRY_NAME.match(entry.name):
            _unlink(entry.path)


def reset() -> None:
    """
    Forget the memoized digests, and allow `store` to prune again.

    A test that changes `DETREE_OPT` or a reader's source between two reads
    needs this; nothing in a normal read path calls it.
    """
    global _generation, _pruned
    _generation = None
    _pruned = False
    _source_digests.clear()


def directory() -> Path | None:
    """
    The directory that holds the compiled modules, or `None` when disabled.

    `DISK_ROOT` wins when it is set.  Otherwise `$UPROOT_CUSTOM_DETREE_CACHE=0`
    disables the level, `$UPROOT_CUSTOM_DETREE_CACHE_DIR` replaces the location,
    and the default is `__pycache__/detree` beside this package.  The default is
    located through `importlib.util.cache_from_source`, so `PYTHONPYCACHEPREFIX`
    and `sys.pycache_prefix` are honoured the way they are for `.pyc` files.

    The directory is not created here; `store` creates it when it has something
    to write.
    """
    if DISK_ROOT is not None:
        return DISK_ROOT
    if os.environ.get(DISABLE_ENV, "") == "0":
        return None
    override = os.environ.get(DIRECTORY_ENV)
    if override:
        return Path(override)
    try:
        import importlib.util

        target = importlib.util.cache_from_source(str(_HERE / "__init__.py"))
    except (NotImplementedError, ValueError):  # pragma: no cover - unusual builds
        return None
    return Path(target).parent / "detree"


def generation() -> str:
    """
    A digest of everything but the reader that decides what a module looks like.

    Editing the compiler, upgrading either package, changing the ISA version or
    setting `DETREE_OPT=0` produces a new generation.  Entries of another
    generation are never read, because the generation is part of the file name.
    """
    global _generation
    if _generation is None:
        parts = [
            "compiler=" + _compiler_digest(),
            "detree=" + _detree_digest(),
            "uproot_custom=" + _package_version("uproot-custom"),
            "detree_vm=" + _package_version("detree-vm"),
            "isa=" + _isa_version(),
            "opt=" + ("0" if os.environ.get("DETREE_OPT") == "0" else "1"),
            "cache_tag=" + str(sys.implementation.cache_tag),
        ]
        _generation = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return _generation


def key_for(signature: str, reader: Reader) -> str:
    """
    The disk key of one compiled reader tree.

    Args:
        signature: what `describe_reader` reports for the tree.
        reader: the root of the tree, whose classes' source files are hashed.

    Returns:
        A hex digest that changes when the tree, its source or the compiler
        changes.
    """
    parts = [generation(), signature]
    parts.extend(f"{path}:{_file_digest(Path(path))}" for path in _reader_sources(reader))
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def load(key: str) -> bytes | None:
    """
    Read the entry *key*.

    An entry that no longer parses as a module is deleted and reported as a
    miss, so a truncated write or a stray file costs one recompilation rather
    than a broken read.  Parsing and validating costs about 80 µs against a
    compile of several milliseconds, and the machine parses the bytes again when
    the read runs, so this is the only place where a bad entry can still turn
    into a recompile instead of a failed read.

    Args:
        key: the digest `key_for` returned.

    Returns:
        The module bytes, or `None` when no entry of this generation matches.

    Raises:
        ValueError: *key* is not a digest `key_for` could have produced.
    """
    if not _KEY_NAME.match(key):
        raise ValueError(f"{key!r} is not a compiled-module digest")
    root = directory()
    if root is None:
        return None
    path = root / f"{generation()[:8]}-{key}.mod"
    try:
        codes = path.read_bytes()
    except OSError:
        return None
    if not _valid(codes):
        STATS["read_errors"] += 1
        _unlink(path)
        return None
    STATS["disk_hits"] += 1
    return codes


def store(key: str, codes: bytes) -> bool:
    """
    Write one entry, atomically, and delete the entries of other generations.

    A failure is counted and never raised: a read-only install or a full disk
    must not break a read that already holds the bytes.

    Args:
        key: the digest `key_for` returned.
        codes: the module bytes to write.

    Returns:
        Whether the entry reached the disk.

    Raises:
        ValueError: *key* is not a digest `key_for` could have produced, so no
            entry name would ever match the file.
    """
    if not _KEY_NAME.match(key):
        raise ValueError(f"{key!r} is not a compiled-module digest")
    root = directory()
    if root is None or sys.dont_write_bytecode:
        return False

    target = root / f"{generation()[:8]}-{key}.mod"
    temporary: Path | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        prune(root)
        with tempfile.NamedTemporaryFile(
            dir=root, prefix=".tmp-", suffix=".mod", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(codes)
        os.replace(temporary, target)
    except OSError:
        STATS["write_errors"] += 1
        if temporary is not None:
            _unlink(temporary)
        return False
    STATS["writes"] += 1
    return True


def prune(root: Path) -> None:
    """
    Delete the entries of other generations, once per process.

    Only names `store` produces are touched, so a temporary file another process
    is writing is never removed; one older than `_TEMPORARY_AGE` is treated as
    abandoned, which is how a write that died mid-way is cleaned up.  An older
    process that loses its entries here recompiles them, which is the same cost
    as a cache miss.
    """
    global _pruned
    if _pruned:
        return
    _pruned = True
    current = generation()[:8] + "-"
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        if _ENTRY_NAME.match(entry.name):
            if not entry.name.startswith(current):
                _unlink(entry.path)
        elif _TEMPORARY_NAME.match(entry.name) and _aged(entry, _TEMPORARY_AGE):
            _unlink(entry.path)


def _unlink(path: str | Path) -> None:
    """
    Delete *path*, treating a failure to do so as nothing to report.
    """
    try:
        os.unlink(path)
    except OSError:
        pass


def _aged(entry: os.DirEntry, seconds: float) -> bool:
    """
    Whether *entry* was last modified more than *seconds* ago.
    """
    try:
        modified = entry.stat(follow_symlinks=False).st_mtime
    except OSError:  # pragma: no cover - the file vanished mid-scan
        return False
    return modified < time.time() - seconds


def _reader_sources(reader: Reader) -> list[str]:
    """
    The source files that decide one reader tree's module, sorted and unique.

    Every class on a reader's MRO counts, not only the concrete one: a reader
    may inherit a method from a base class, and the frontend compiles with
    `inspect.getsource` of the method, which resolves to the class that defines
    it.  A base class in another file changes the module just as much as the
    concrete class does.
    """
    from uproot_custom.detree.compiler.frontend import _reader_children

    files: set[str] = set()

    def add(node) -> None:
        for klass in type(node).__mro__:
            if klass.__module__ == "builtins":
                continue
            try:
                path = inspect.getsourcefile(klass)
            except TypeError:  # pragma: no cover - a class without a file
                path = None
            if path:
                files.add(path)

    def walk(node) -> None:
        add(node)
        for _, child, _ in _reader_children(node):
            walk(child)

    walk(reader)
    return sorted(files)


def _file_digest(path: Path) -> str:
    """
    The sha256 of one source file, memoized until its mtime or size changes.
    """
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    memo = (str(path), stat.st_mtime_ns, stat.st_size)
    digest = _source_digests.get(memo)
    if digest is None:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:  # pragma: no cover - a file that vanished mid-read
            return "unreadable"
        if len(_source_digests) > 512:
            _source_digests.clear()
        _source_digests[memo] = digest
    return digest


def _compiler_digest() -> str:
    """
    The digest of the code that turns a reader into a module.
    """
    files = list((_HERE / "compiler").rglob("*.py")) + [_HERE / "decl.py"]
    parts = [
        path.relative_to(_HERE).as_posix() + ":" + _file_digest(path) for path in sorted(files)
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _detree_digest() -> str:
    """
    Detree's own source when it is installed in development mode.

    A released Detree is identified by its version.  An editable install keeps
    one version string while its source changes, and Detree decides what a
    module looks like as much as this package does, so there the files
    themselves have to enter the generation.
    """
    if not _editable("detree-vm"):
        return "released"
    try:
        import detree
    except ImportError:  # pragma: no cover - Detree is a hard dependency
        return "missing"
    package = getattr(detree, "__file__", None)
    if package is None:  # pragma: no cover - a namespace package
        return "unknown"
    root = Path(package).resolve().parent
    parts = [
        path.relative_to(root).as_posix() + ":" + _file_digest(path)
        for path in sorted(root.rglob("*.py"))
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _editable(distribution: str) -> bool:
    """
    Whether *distribution* was installed from a directory, per PEP 610.

    `direct_url.json` is the record the installer leaves behind; without it the
    distribution came from an index, and its version identifies its code.
    """
    try:
        from importlib.metadata import distribution as get_distribution

        direct_url = get_distribution(distribution).read_text("direct_url.json")
    except Exception:  # not installed, or no metadata
        return False
    if not direct_url:
        return False
    try:
        return bool(json.loads(direct_url).get("dir_info", {}).get("editable", False))
    except (ValueError, AttributeError):
        return False


def _package_version(distribution: str) -> str:
    """
    The installed version of a distribution, or `unknown`.
    """
    try:
        from importlib.metadata import version

        return version(distribution)
    except Exception:  # not installed as a distribution, or no metadata
        return "unknown"


def _isa_version() -> str:
    """
    The Detree ISA version, or `unknown` when Detree cannot be imported.
    """
    try:
        from detree.spec.isa import ISA_MAJOR, ISA_MINOR
    except Exception:  # pragma: no cover - Detree is a hard dependency
        return "unknown"
    return f"{ISA_MAJOR}.{ISA_MINOR}"


def _valid(codes: bytes) -> bool:
    """
    Whether *codes* still parses and validates as a Detree module.
    """
    try:
        from detree.spec.module import Module
        from detree.spec.validate import validate_module

        validate_module(Module.from_bytes(codes))
    except Exception:
        return False
    return True


__all__ = [
    "DIRECTORY_ENV",
    "DISABLE_ENV",
    "DISK_ROOT",
    "STATS",
    "clear",
    "clear_disk",
    "directory",
    "generation",
    "get",
    "key_for",
    "load",
    "prune",
    "put",
    "reset",
    "size",
    "store",
]
