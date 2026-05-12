"""Tests for cc_tts.config — TDD RED phase."""

from __future__ import annotations

from pathlib import Path

from cc_tts.config import TTSConfig, load_config


class TestTTSConfigDefaults:
    def test_defaults(self) -> None:
        config = TTSConfig()
        assert config.engine == "auto"
        assert config.voice == "en_US-amy-medium"
        assert config.speed == 1.0
        assert config.auto_read is False
        assert config.max_chars == 2000
        assert config.player == "auto"


class TestLoadConfigFromToml:
    def test_loads_from_toml_file(self, tmp_path: Path, monkeypatch: object) -> None:
        import pytest

        mp = pytest.MonkeyPatch()  # noqa: F841
        toml_content = b'[tts]\nengine = "espeak"\nvoice = "en_GB-alan"\nspeed = 1.5\n'
        config_file = tmp_path / ".cc-senses.toml"
        config_file.write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        config = load_config()
        assert config.engine == "espeak"
        assert config.voice == "en_GB-alan"
        assert config.speed == 1.5

    def test_returns_defaults_when_no_toml(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        config = load_config()
        assert config.engine == "auto"


class TestEnvOverrides:
    def test_env_overrides_toml(self, tmp_path: Path, monkeypatch: object) -> None:
        toml_content = b'[tts]\nengine = "espeak"\n'
        config_file = tmp_path / ".cc-senses.toml"
        config_file.write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        monkeypatch.setenv("CC_TTS_ENGINE", "piper")  # type: ignore[union-attr]
        config = load_config()
        assert config.engine == "piper"

    def test_bool_env_parsing(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        monkeypatch.setenv("CC_TTS_AUTO_READ", "true")  # type: ignore[union-attr]
        config = load_config()
        assert config.auto_read is True

    def test_numeric_env_parsing(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        monkeypatch.setenv("CC_TTS_SPEED", "1.8")  # type: ignore[union-attr]
        monkeypatch.setenv("CC_TTS_MAX_CHARS", "500")  # type: ignore[union-attr]
        config = load_config()
        assert config.speed == 1.8
        assert config.max_chars == 500
