import glob
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def test_downstream_build(tmpdir: Path):
    # Build wheel for `uproot-custom`
    subprocess.run(
        ["python", "-m", "build", "-w", "-o", str(tmpdir)],
        check=True,
        cwd=Path(__file__).parent.parent,
    )

    wheel_files = glob.glob(str(tmpdir / "*.whl"))
    assert len(wheel_files) == 1, "Expected exactly one wheel file to be created."
    wheel_path = wheel_files[0]

    # prepare the test project
    example_path = Path(__file__).parent.parent / "example"

    shutil.copytree(example_path / "cpp", tmpdir / "cpp")
    shutil.copytree(example_path / "my_reader", tmpdir / "my_reader")

    pyproject_toml = (
        Path(__file__).parent / "test_downstream_build_pyproject.toml"
    ).read_text(encoding="utf-8")

    pyproject_toml = pyproject_toml.replace("@wheel-path@", str(wheel_path.replace("\\", "/")))

    (tmpdir / "pyproject.toml").write_text(pyproject_toml, encoding="utf-8")

    # Build the downstream project
    subprocess.run(
        ["python", "-m", "build", "-w", "-o", str(tmpdir)],
        check=True,
        cwd=tmpdir,
    )
