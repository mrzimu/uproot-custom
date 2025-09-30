from pathlib import Path

import pytest
import uproot


@pytest.fixture(scope="session")
def f_test_data():
    yield uproot.open(Path(__file__).parent / "test-data.root")
