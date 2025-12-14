import uproot_custom
import uproot_custom.factories


def test_AsCustom_py_arrays(f_test_data, test_branches, subtests, monkeypatch):
    monkeypatch.setattr(uproot_custom.factories, "reader_backend", "python")
    assert uproot_custom.factories.reader_backend == "python"

    for sub_branch_path in test_branches:
        with subtests.test(sub_branch_path=sub_branch_path):
            f_test_data[sub_branch_path].array()


def test_AsCustom_py_virtual(f_test_data, test_branches, subtests, monkeypatch):
    monkeypatch.setattr(uproot_custom.factories, "reader_backend", "python")
    assert uproot_custom.factories.reader_backend == "python"

    for sub_branch_path in test_branches:
        with subtests.test(sub_branch_path=sub_branch_path):
            f_test_data[sub_branch_path].arrays(virtual=True)
