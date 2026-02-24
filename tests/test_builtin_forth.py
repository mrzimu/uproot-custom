import pytest

import uproot_custom
import uproot_custom.factories


def test_AsCustom_forth_arrays(f_test_data, test_branches, subtests, monkeypatch):
    monkeypatch.setattr(uproot_custom.factories, "reader_backend", "forth")
    assert uproot_custom.factories.reader_backend == "forth"

    with pytest.warns(UserWarning):
        for sub_branch_path in test_branches:
            with subtests.test(sub_branch_path=sub_branch_path):
                f_test_data[sub_branch_path].array()


def test_AsCustom_forth_virtual(f_test_data, test_branches, subtests, monkeypatch):
    monkeypatch.setattr(uproot_custom.factories, "reader_backend", "forth")
    assert uproot_custom.factories.reader_backend == "forth"

    for sub_branch_path in test_branches:
        with subtests.test(sub_branch_path=sub_branch_path):
            f_test_data[sub_branch_path].arrays(virtual=True)
