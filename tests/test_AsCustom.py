def test_to_packed(test_contexts):
    br = test_contexts["primitive"]["file"]["/tree:branch/m_double"]

    assert br.array(entry_start=0, entry_stop=1).nbytes == 8
    assert br.array(entry_start=0, entry_stop=10).nbytes == 80


def test_virtual(test_contexts, subtests):
    for test_name, ctx in test_contexts.items():
        test_file = ctx["file"]
        test_branches = ctx["branches"]
        for sub_branch in test_branches:
            with subtests.test(test_name=test_name, branch=sub_branch):
                test_file[sub_branch].arrays(virtual=True)
