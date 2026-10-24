"""Tests for `setup_models --install-runtime / --write-config` (#118).

- `.cc-senses.toml` upsert across its four states (missing / no [vlm] /
  matching [vlm] / divergent [vlm]) — the original file is never rewritten
  when it already holds a different [vlm].
- Runtime install dispatch with subprocess mocked.
"""

from __future__ import annotations

import io
import subprocess
import tomllib
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cc_vlm import setup_models
from cc_vlm.setup_models import ModelSpec, install_runtime, main, upsert_vlm_config

SNIPPET = '[vlm]\nhandler_name = "moondream"\nmodel_path = "/m.gguf"\nmmproj_path = "/p.gguf"'

LLAMACPP = ModelSpec(
    key="m",
    title="M",
    engine="llamacpp",
    handler_name="moondream",
    model_url="https://h/m.gguf",
    mmproj_url="https://h/p.gguf",
)
LLAMASERVER = ModelSpec(
    key="s",
    title="S",
    engine="llamaserver",
    server_url="http://127.0.0.1:8080",
    model_url="https://h/m.gguf",
    mmproj_url="https://h/p.gguf",
)


# --- .cc-senses.toml upsert: the four states ---


class TestUpsertVlmConfig:
    def test_missing_file_is_created_with_vlm_only(self, tmp_path: Path) -> None:
        config = tmp_path / ".cc-senses.toml"
        assert upsert_vlm_config(SNIPPET, config) == "created"
        assert tomllib.loads(config.read_text()) == tomllib.loads(SNIPPET)

    def test_file_without_vlm_gets_section_appended(self, tmp_path: Path) -> None:
        config = tmp_path / ".cc-senses.toml"
        config.write_text('[tts]\nengine = "kokoro"')
        assert upsert_vlm_config(SNIPPET, config) == "appended"
        parsed = tomllib.loads(config.read_text())
        assert parsed["tts"] == {"engine": "kokoro"}
        assert parsed["vlm"] == tomllib.loads(SNIPPET)["vlm"]

    def test_matching_vlm_is_a_noop(self, tmp_path: Path) -> None:
        config = tmp_path / ".cc-senses.toml"
        original = f'[tts]\nengine = "kokoro"\n\n{SNIPPET}\n'
        config.write_text(original)
        assert upsert_vlm_config(SNIPPET, config) == "unchanged"
        assert config.read_text() == original
        assert not (tmp_path / ".cc-senses.toml.proposed").exists()

    def test_divergent_vlm_writes_proposed_and_keeps_original(self, tmp_path: Path) -> None:
        config = tmp_path / ".cc-senses.toml"
        original = '[vlm]\nhandler_name = "qwen2.5vl"\nmodel_path = "/other.gguf"\n'
        config.write_text(original)
        assert upsert_vlm_config(SNIPPET, config) == "proposed"
        assert config.read_text() == original
        proposed = tmp_path / ".cc-senses.toml.proposed"
        assert tomllib.loads(proposed.read_text()) == tomllib.loads(SNIPPET)


# --- runtime install dispatch ---


@pytest.fixture
def no_llama_cpp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_models, "_llama_cpp_installed", lambda: False)
    monkeypatch.setattr(setup_models.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup_models.shutil, "which", lambda _name: None)
    monkeypatch.delenv("CC_VLM_LLAMA_CPP_INDEX", raising=False)


class TestInstallRuntime:
    @pytest.mark.usefixtures("no_llama_cpp")
    def test_llamacpp_installs_cpu_wheel(self) -> None:
        with patch.object(setup_models.subprocess, "run") as run:
            assert install_runtime(LLAMACPP) is True
        argv = run.call_args.args[0]
        assert argv[:4] == ["uv", "pip", "install", "llama-cpp-python"]
        assert argv[-1] == "https://abetlen.github.io/llama-cpp-python/whl/cpu"

    @pytest.mark.usefixtures("no_llama_cpp")
    def test_index_override_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CC_VLM_LLAMA_CPP_INDEX", "https://example.test/whl")
        with patch.object(setup_models.subprocess, "run") as run:
            assert install_runtime(LLAMACPP) is True
        assert run.call_args.args[0][-1] == "https://example.test/whl"

    @pytest.mark.usefixtures("no_llama_cpp")
    def test_failed_install_returns_false_and_prints_hint(self) -> None:
        out = io.StringIO()
        error = subprocess.CalledProcessError(1, ["uv"])
        with patch.object(setup_models.subprocess, "run", side_effect=error), redirect_stdout(out):
            assert install_runtime(LLAMACPP) is False
        assert "uv pip install llama-cpp-python" in out.getvalue()

    def test_llamacpp_already_installed_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup_models, "_llama_cpp_installed", lambda: True)
        with patch.object(setup_models.subprocess, "run") as run:
            assert install_runtime(LLAMACPP) is True
        run.assert_not_called()

    def test_llamaserver_missing_binary_fails_without_installing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(setup_models.shutil, "which", lambda _name: None)
        with patch.object(setup_models.subprocess, "run") as run, redirect_stdout(io.StringIO()):
            assert install_runtime(LLAMASERVER) is False
        run.assert_not_called()


# --- CLI wiring ---


class TestMainFlags:
    def _run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *flags: str) -> MagicMock:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(setup_models, "MODELS_DIR", tmp_path / "models")
        monkeypatch.setattr(setup_models, "download", lambda _url, _dest: False)
        install = MagicMock(return_value=True)
        monkeypatch.setattr(setup_models, "install_runtime", install)
        with redirect_stdout(io.StringIO()):
            assert main(["moondream", *flags]) == 0
        return install

    def test_default_prints_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install = self._run(tmp_path, monkeypatch)
        install.assert_not_called()
        assert not (tmp_path / ".cc-senses.toml").exists()

    def test_flags_install_and_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install = self._run(tmp_path, monkeypatch, "--install-runtime", "-w")
        install.assert_called_once()
        parsed = tomllib.loads((tmp_path / ".cc-senses.toml").read_text())
        assert parsed["vlm"]["handler_name"] == "moondream"

    def test_unknown_flag_is_rejected(self) -> None:
        with redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
            assert main(["moondream", "--bogus"]) != 0
