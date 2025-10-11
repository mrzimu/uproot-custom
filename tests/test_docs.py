import subprocess

import pytest

pytest.importorskip("sphinx")


def test_build_docs(base_dir_path):
    """Test that the Sphinx documentation builds without errors."""
    result = subprocess.run(
        ["sphinx-build", "-b", "html", f"{base_dir_path}/docs/", f"{base_dir_path}/build/html"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Sphinx build failed:\n{result.stderr}"
