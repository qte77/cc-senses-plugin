"""Tests for cc_stt.config — TDD RED phase."""

from __future__ import annotations

from pathlib import Path

from cc_stt.config import STTConfig, load_stt_config


class TestSTTConfigDefaults:
    def test_defaults(self) -> None:
        config = STTConfig()
        assert config.engine == "auto"
        assert config.language == "en"
        assert config.wake_word == "hey_claude"
        assert config.mic_device == "default"
        assert config.auto_listen is False
        assert config.strip_fillers is True
        assert config.intent_match is True
        assert config.max_words == 200

    def test_default_is_not_mutable_across_instances(self) -> None:
        a = STTConfig()
        b = STTConfig()
        a.language = "de"
        assert b.language == "en"


class TestLoadSTTConfigFromToml:
    def test_loads_from_cc_senses_toml_stt_section(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        toml_content = b'[stt]\nengine = "moonshine"\nlanguage = "de"\n'
        config_file = tmp_path / ".cc-senses.toml"
        config_file.write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        config = load_stt_config()
        assert config.engine == "moonshine"
        assert config.language == "de"

    def test_returns_defaults_when_no_toml(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        config = load_stt_config()
        assert config.engine == "auto"

    def test_returns_defaults_when_no_stt_section(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        toml_content = b'[tts]\nengine = "piper"\n'
        config_file = tmp_path / ".cc-senses.toml"
        config_file.write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        config = load_stt_config()
        assert config.engine == "auto"


class TestSTTEnvOverrides:
    def test_env_overrides_toml(self, tmp_path: Path, monkeypatch: object) -> None:
        toml_content = b'[stt]\nengine = "moonshine"\n'
        config_file = tmp_path / ".cc-senses.toml"
        config_file.write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        monkeypatch.setenv("CC_STT_ENGINE", "vosk")  # type: ignore[union-attr]
        config = load_stt_config()
        assert config.engine == "vosk"

    def test_bool_env_parsing(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        monkeypatch.setenv("CC_STT_AUTO_LISTEN", "true")  # type: ignore[union-attr]
        config = load_stt_config()
        assert config.auto_listen is True

    def test_string_env_override(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        monkeypatch.setenv("CC_STT_MIC_DEVICE", "hw:1,0")  # type: ignore[union-attr]
        config = load_stt_config()
        assert config.mic_device == "hw:1,0"
