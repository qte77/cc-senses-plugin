"""Smoke tests for Makefile setup_* targets.

Verifies the targets exist and dry-run-print the expected commands.
Run via `make -n <target>`; output is parsed for required substrings.
URL constants are parsed directly from the Makefile to avoid a subprocess.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"

HF_URL_RE = re.compile(r"^https://huggingface\.co/[^/]+/[^/]+/resolve/main/[^/]+\.gguf$")
URL_VAR_RE = re.compile(r"^(VLM_\w+_URL)\s*:=\s*(\S+)\s*$", re.MULTILINE)


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _url_vars() -> dict[str, str]:
    return {m.group(1): m.group(2) for m in URL_VAR_RE.finditer(_makefile_text())}


def _phony_line() -> str:
    """Return the full .PHONY declaration with continuations folded into one line."""
    text = _makefile_text()
    match = re.search(r"^\.PHONY:\s*((?:.*\\\n)*.*)$", text, re.MULTILINE)
    assert match, ".PHONY declaration missing"
    return match.group(1).replace("\\\n", " ")


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


class TestVLMUrlConstants:
    """The four dead URL sources (ggml-org/moondream2-20250414-GGUF + bartowski 3B)
    must be replaced with canonical / mirror repos, and four new URLs for the
    llamaserver opt-in targets must exist."""

    def test_moondream_uses_canonical_repo(self) -> None:
        urls = _url_vars()
        assert "moondream/moondream2-gguf" in urls["VLM_MOONDREAM_MODEL_URL"]
        assert "moondream/moondream2-gguf" in urls["VLM_MOONDREAM_MMPROJ_URL"]
        # Dead repo must be gone
        assert "ggml-org/moondream2-20250414-GGUF" not in _makefile_text()

    def test_qwen25_uses_lmstudio_mirror(self) -> None:
        urls = _url_vars()
        assert "lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF" in urls["VLM_QWEN25_MODEL_URL"]
        assert "lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF" in urls["VLM_QWEN25_MMPROJ_URL"]
        # Removed bartowski 3B repo must be gone
        assert "bartowski/Qwen2.5-VL-3B-Instruct-GGUF" not in _makefile_text()

    def test_qwen3vl_url_constants_present(self) -> None:
        urls = _url_vars()
        assert "VLM_QWEN3VL_MODEL_URL" in urls
        assert "VLM_QWEN3VL_MMPROJ_URL" in urls
        assert "Qwen/Qwen3-VL-2B-Instruct-GGUF" in urls["VLM_QWEN3VL_MODEL_URL"]
        assert "Qwen/Qwen3-VL-2B-Instruct-GGUF" in urls["VLM_QWEN3VL_MMPROJ_URL"]

    def test_smolvlm_url_constants_present(self) -> None:
        urls = _url_vars()
        assert "VLM_SMOLVLM_MODEL_URL" in urls
        assert "VLM_SMOLVLM_MMPROJ_URL" in urls
        assert "ggml-org/SmolVLM-500M-Instruct-GGUF" in urls["VLM_SMOLVLM_MODEL_URL"]
        assert "ggml-org/SmolVLM-500M-Instruct-GGUF" in urls["VLM_SMOLVLM_MMPROJ_URL"]

    def test_all_url_constants_have_valid_hf_shape(self) -> None:
        urls = _url_vars()
        # Must be at least 8 URL vars (4 in-process + 4 llamaserver) after the fix
        assert len(urls) >= 8, f"expected >=8 VLM_*_URL constants, got {sorted(urls)}"
        for name, url in urls.items():
            assert HF_URL_RE.match(url), f"{name} has unexpected URL shape: {url!r}"


class TestNewSetupTargets:
    def test_setup_see_qwen3vl_target_exists(self, make_available: None) -> None:
        result = _make_dry_run("setup_see_qwen3vl")
        assert result.returncode == 0, f"setup_see_qwen3vl target missing — stderr: {result.stderr}"

    def test_setup_see_smolvlm_target_exists(self, make_available: None) -> None:
        result = _make_dry_run("setup_see_smolvlm")
        assert result.returncode == 0, f"setup_see_smolvlm target missing — stderr: {result.stderr}"

    def test_setup_default_all_target_exists(self, make_available: None) -> None:
        result = _make_dry_run("setup_default_all")
        assert result.returncode == 0, f"setup_default_all target missing — stderr: {result.stderr}"


class TestLlamaserverSnippets:
    """Opt-in llamaserver targets must print a [vlm] block with engine="llamaserver"
    and the loopback server_url."""

    @pytest.mark.parametrize("target", ["setup_see_qwen3vl", "setup_see_smolvlm"])
    def test_prints_llamaserver_engine_and_server_url(
        self, make_available: None, target: str
    ) -> None:
        result = _make_dry_run(target)
        assert 'engine = "llamaserver"' in result.stdout
        assert 'server_url = "http://127.0.0.1:8080"' in result.stdout


class TestInProcessSnippetsRegression:
    """In-process targets must NOT print the llamaserver engine key — guards
    against copy-paste of the new snippet template into the old recipes."""

    def test_setup_see_does_not_print_llamaserver_engine(self, make_available: None) -> None:
        result = _make_dry_run("setup_see")
        assert 'engine = "llamaserver"' not in result.stdout

    def test_setup_see_qwen25_does_not_print_llamaserver_engine(self, make_available: None) -> None:
        result = _make_dry_run("setup_see_qwen25")
        assert 'engine = "llamaserver"' not in result.stdout


class TestSetupDefaultAll:
    """The kitchen-sink target must transitively run the in-process default
    (setup_see/Moondream2) — not the opt-in llamaserver paths."""

    def test_default_all_pulls_in_moondream(self, make_available: None) -> None:
        result = _make_dry_run("setup_default_all")
        assert "moondream2-text-model" in result.stdout

    def test_default_all_does_not_pull_in_qwen3vl(self, make_available: None) -> None:
        result = _make_dry_run("setup_default_all")
        assert "Qwen3VL-2B-Instruct" not in result.stdout

    def test_default_all_does_not_pull_in_smolvlm(self, make_available: None) -> None:
        result = _make_dry_run("setup_default_all")
        assert "SmolVLM-500M-Instruct" not in result.stdout


class TestPhony:
    """The three new targets must be on the .PHONY line."""

    @pytest.mark.parametrize(
        "target", ["setup_see_qwen3vl", "setup_see_smolvlm", "setup_default_all"]
    )
    def test_phony_lists_new_target(self, target: str) -> None:
        assert target in _phony_line()


class TestFilenamesMatchUrlBasenames:
    """Each setup_see* recipe writes the downloaded file to a path whose basename
    must match the URL basename — guards against the prior bug class where the
    Makefile asked curl for `f16.gguf` but saved as `f16_ct-q4_0.gguf`."""

    @pytest.mark.parametrize(
        ("target", "model_var", "mmproj_var"),
        [
            ("setup_see", "VLM_MOONDREAM_MODEL_URL", "VLM_MOONDREAM_MMPROJ_URL"),
            ("setup_see_qwen25", "VLM_QWEN25_MODEL_URL", "VLM_QWEN25_MMPROJ_URL"),
            ("setup_see_qwen3vl", "VLM_QWEN3VL_MODEL_URL", "VLM_QWEN3VL_MMPROJ_URL"),
            ("setup_see_smolvlm", "VLM_SMOLVLM_MODEL_URL", "VLM_SMOLVLM_MMPROJ_URL"),
        ],
    )
    def test_recipe_paths_match_url_basenames(
        self,
        make_available: None,
        target: str,
        model_var: str,
        mmproj_var: str,
    ) -> None:
        urls = _url_vars()
        assert model_var in urls and mmproj_var in urls, (
            f"URL constants missing for {target}: need {model_var}, {mmproj_var}"
        )
        result = _make_dry_run(target)
        assert result.returncode == 0, f"{target} dry-run failed: {result.stderr}"
        model_basename = urls[model_var].rsplit("/", 1)[-1]
        mmproj_basename = urls[mmproj_var].rsplit("/", 1)[-1]
        assert model_basename in result.stdout, (
            f"{target}: recipe does not save to URL basename {model_basename!r}"
        )
        assert mmproj_basename in result.stdout, (
            f"{target}: recipe does not save to URL basename {mmproj_basename!r}"
        )
