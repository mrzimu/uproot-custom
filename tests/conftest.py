from pathlib import Path

import pytest
import uproot


@pytest.fixture(scope="session")
def test_data_path():
    yield Path(__file__).parent / "test-data.root"


@pytest.fixture(scope="session")
def f_test_data(test_data_path):
    yield uproot.open(test_data_path)
