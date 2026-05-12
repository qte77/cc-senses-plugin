"""Smoke tests for Makefile setup_* targets.

Verifies the targets exist and dry-run-print the expected commands.
Run via `make -n <target>`; output is parsed for required substrings.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def make_available() -> None:
    if shutil.which("make") is None:
        pytest.skip("make not available in this environment")


def _make_dry_run(target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class TestSetupSee:
    def test_setup_see_target_exists(self, make_available: None) -> None:
        result = _make_dry_run("setup_see")
        assert result.returncode == 0, f"setup_see target missing — stderr: {result.stderr}"

    def test_setup_see_runs_uv_sync_with_see_extra(self, make_available: None) -> None:
        result = _make_dry_run("setup_see")
        assert "uv sync --extra see" in result.stdout

    def test_setup_see_references_moondream_model(self, make_available: None) -> None:
        """Default downloads must point at Moondream2 GGUF + mmproj."""
        result = _make_dry_run("setup_see")
        out = result.stdout.lower()
        assert "moondream" in out

    def test_setup_see_does_not_reference_qwen25_as_default(self, make_available: None) -> None:
        """The Qwen2.5-VL alt is in setup_see_qwen25, not the default target."""
        result = _make_dry_run("setup_see")
        # The dry-run output for setup_see should not pull in Qwen2.5-VL URLs.
        assert "qwen2.5-vl" not in result.stdout.lower()


class TestSetupSeeQwen25:
    def test_setup_see_qwen25_target_exists(self, make_available: None) -> None:
        result = _make_dry_run("setup_see_qwen25")
        assert result.returncode == 0, f"setup_see_qwen25 target missing — stderr: {result.stderr}"

    def test_setup_see_qwen25_references_qwen25_model(self, make_available: None) -> None:
        result = _make_dry_run("setup_see_qwen25")
        assert "Qwen2.5-VL" in result.stdout
