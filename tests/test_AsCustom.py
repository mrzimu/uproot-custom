def test_to_packed(f_test_data):
    br = f_test_data["/my_tree:basic_types/m_double"]

    assert br.array(entry_start=0, entry_stop=1).nbytes == 8
    assert br.array(entry_start=0, entry_stop=10).nbytes == 80
