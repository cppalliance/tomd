"""Smoke tests for the tomd CLI entry point."""

import subprocess
import sys

import pytest


def test_tomd_module_invokable_via_python():
    """`python -m tomd.main --help` must succeed when tomd is installed."""
    try:
        import tomd.main  # noqa: F401
    except ImportError:
        pytest.skip("tomd not installed as a package (run `pip install -e .`)")
    result = subprocess.run(
        [sys.executable, "-m", "tomd.main", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "tomd" in result.stdout
