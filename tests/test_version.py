"""Exercise release targets in isolated copies without bumping this checkout."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "target,version",
    [
        ("bump-patch", "2.3.5"),
        ("bump-minor", "2.4.0"),
        ("bump-major", "3.0.0"),
        ("bump-version", "4.5.6"),
        ("version", "2.3.4"),
        ("check-version", "2.3.4"),
    ],
)
def test_version_targets(tmp_path: Path, target: str, version: str) -> None:
    """Run Make targets against a fixture and preserve unrelated metadata."""
    import sys

    (tmp_path / "scripts").mkdir()
    (tmp_path / "src/subfork").mkdir(parents=True)
    shutil.copy(ROOT / "Makefile", tmp_path)
    shutil.copy(ROOT / "scripts/bump-version.py", tmp_path / "scripts")
    project = tmp_path / "pyproject.toml"
    init = tmp_path / "src/subfork/__init__.py"
    project.write_text('[project]\nname = "subfork"\nversion = "2.3.4"\n')
    init.write_text('__version__ = "2.3.4"\n')
    result = subprocess.run(
        ["make", target, "PYTHON=" + sys.executable, "VERSION=4.5.6"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert version in result.stdout
    assert project.read_text() == '[project]\nname = "subfork"\nversion = "' + version + '"\n'
    assert init.read_text() == '__version__ = "' + version + '"\n'
    # A mismatch must fail before either file is changed.
    init.write_text('__version__ = "9.9.9"\n')
    before = project.read_text()
    result = subprocess.run(
        [sys.executable, "scripts/bump-version.py", "--bump", "patch"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert project.read_text() == before
    assert init.read_text() == '__version__ = "9.9.9"\n'
