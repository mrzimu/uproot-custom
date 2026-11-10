"""
The module-level `claim`, `release` and `clear_claims` entry points.

Every test replaces `AsCustom.target_branches` through `monkeypatch`, because
`conftest.py` claims the fixture branches when it is imported: a test that ran
against the session set could not tell a working `claim` from one that did
nothing.
"""

from pathlib import Path

import pytest
import uproot

import uproot_custom

DATA = Path(__file__).parent / "data"


@pytest.fixture
def empty_claims(monkeypatch):
    """
    An empty claim set, restored when the test ends.
    """
    monkeypatch.setattr(uproot_custom.AsCustom, "target_branches", set())
    return uproot_custom.AsCustom.target_branches


def test_claim_regularizes_cycle_number(empty_claims):
    uproot_custom.claim("/tree;1:branch/m_int")

    assert empty_claims == {"/tree:branch/m_int"}


def test_claim_is_idempotent(empty_claims):
    uproot_custom.claim("/tree:branch/m_int")
    uproot_custom.claim("/tree:branch/m_int")
    uproot_custom.claim("/tree;7:branch/m_int")

    assert empty_claims == {"/tree:branch/m_int"}


@pytest.mark.parametrize("form", ["str", "list", "tuple", "set", "generator"])
def test_claim_accepts_str_or_iterable(empty_claims, form):
    path = "/tree:branch/m_int"
    paths = {
        "str": path,
        "list": [path],
        "tuple": (path,),
        "set": {path},
        "generator": (cur for cur in [path]),
    }[form]

    assert uproot_custom.claim(paths) is None
    assert empty_claims == {path}


def test_claim_rejects_non_str(empty_claims):
    with pytest.raises(TypeError):
        uproot_custom.claim(["/tree:branch/m_int", 1])

    # An argument that is neither a str nor iterable fails the same way.
    with pytest.raises(TypeError):
        uproot_custom.claim(1)

    assert empty_claims == set()


def test_release_and_clear(empty_claims):
    uproot_custom.claim(["/tree:branch/m_int", "/tree:branch/m_double"])

    uproot_custom.release("/tree;1:branch/m_int")
    assert empty_claims == {"/tree:branch/m_double"}

    # Releasing a path that was never claimed is not an error.
    uproot_custom.release(["/tree:branch/m_never_claimed"])
    assert empty_claims == {"/tree:branch/m_double"}

    uproot_custom.clear_claims()
    assert empty_claims == set()


def test_claim_matches_a_raw_object_path(empty_claims):
    """
    A path taken straight from `branch.object_path` needs no preparation.
    """
    test_file = uproot.open(DATA / "test_primitive.root")
    branch = test_file["tree/branch/m_int"]

    assert ";1" in branch.object_path
    uproot_custom.claim(branch.object_path)

    assert isinstance(branch.interpretation, uproot_custom.AsCustom)

    # The Python backend is always available, so the read proves the claimed
    # path reaches a factory rather than relying on a compiled extension.
    with uproot_custom.use_backend("python"):
        assert len(branch.array()) == branch.num_entries
