"""Tests for cc_vlm.config — VLMConfig BaseSettings + TOML + env overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from cc_vlm.config import VLMConfig, load_vlm_config


class TestVLMConfigDefaults:
    def test_defaults(self) -> None:
        config = VLMConfig()
        assert config.engine == "auto"
        assert config.model_path == ""
        assert config.mmproj_path == ""
        assert config.handler_name == "moondream"
        assert config.n_ctx == 4096
        assert config.n_gpu_layers == 0
        assert config.max_tokens == 256
        assert config.max_dimension == 768
        assert config.jpeg_quality == 85
        assert config.template == "generic"
        assert config.cache_size == 32


class TestEnvOverrides:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in [
            "CC_VLM_ENGINE",
            "CC_VLM_MODEL_PATH",
            "CC_VLM_MMPROJ_PATH",
            "CC_VLM_HANDLER_NAME",
            "CC_VLM_N_CTX",
            "CC_VLM_N_GPU_LAYERS",
            "CC_VLM_MAX_TOKENS",
            "CC_VLM_MAX_DIMENSION",
            "CC_VLM_JPEG_QUALITY",
            "CC_VLM_TEMPLATE",
            "CC_VLM_CACHE_SIZE",
        ]:
            monkeypatch.delenv(var, raising=False)

    def test_string_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CC_VLM_ENGINE", "llamacpp")
        monkeypatch.setenv("CC_VLM_MODEL_PATH", "/tmp/qwen.gguf")
        monkeypatch.setenv("CC_VLM_MMPROJ_PATH", "/tmp/qwen-mmproj.gguf")
        monkeypatch.setenv("CC_VLM_HANDLER_NAME", "llava15")
        monkeypatch.setenv("CC_VLM_TEMPLATE", "terminal")
        config = VLMConfig()
        assert config.engine == "llamacpp"
        assert config.model_path == "/tmp/qwen.gguf"
        assert config.mmproj_path == "/tmp/qwen-mmproj.gguf"
        assert config.handler_name == "llava15"
        assert config.template == "terminal"

    def test_int_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CC_VLM_N_CTX", "8192")
        monkeypatch.setenv("CC_VLM_N_GPU_LAYERS", "-1")
        monkeypatch.setenv("CC_VLM_MAX_TOKENS", "512")
        monkeypatch.setenv("CC_VLM_MAX_DIMENSION", "1024")
        monkeypatch.setenv("CC_VLM_JPEG_QUALITY", "75")
        monkeypatch.setenv("CC_VLM_CACHE_SIZE", "64")
        config = VLMConfig()
        assert config.n_ctx == 8192
        assert config.n_gpu_layers == -1
        assert config.max_tokens == 512
        assert config.max_dimension == 1024
        assert config.jpeg_quality == 75
        assert config.cache_size == 64

    def test_invalid_int_env_raises_validation_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CC_VLM_MAX_DIMENSION", "not-a-number")
        with pytest.raises(Exception):  # noqa: B017
            VLMConfig()

    def test_env_missing_leaves_defaults(self) -> None:
        config = VLMConfig()
        assert config.engine == "auto"


class TestLoadVLMConfig:
    def test_no_config_file_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        config = load_vlm_config()
        assert config.engine == "auto"
        assert config.model_path == ""

    def test_loads_from_vlm_toml_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".cc-senses.toml").write_text(
            "[vlm]\n"
            'engine = "llamacpp"\n'
            'model_path = "/models/qwen.gguf"\n'
            'mmproj_path = "/models/qwen-mmproj.gguf"\n'
            "n_ctx = 8192\n"
            "max_dimension = 512\n"
        )
        monkeypatch.chdir(tmp_path)
        config = load_vlm_config()
        assert config.engine == "llamacpp"
        assert config.model_path == "/models/qwen.gguf"
        assert config.mmproj_path == "/models/qwen-mmproj.gguf"
        assert config.n_ctx == 8192
        assert config.max_dimension == 512

    def test_env_overrides_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / ".cc-senses.toml").write_text('[vlm]\nmodel_path = "/toml/path.gguf"\n')
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CC_VLM_MODEL_PATH", "/env/path.gguf")
        config = load_vlm_config()
        assert config.model_path == "/env/path.gguf"

    def test_ignores_unknown_vlm_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".cc-senses.toml").write_text(
            '[vlm]\nengine = "llamacpp"\nunknown_field = "should_be_dropped"\n'
        )
        monkeypatch.chdir(tmp_path)
        config = load_vlm_config()
        assert config.engine == "llamacpp"
        assert not hasattr(config, "unknown_field")
