"""Configuration loading from .cc-senses.toml [stt] section and environment variables."""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from cc_voice_common.config import load_toml_section


class STTConfig(BaseSettings):
    """STT plugin configuration."""

    model_config = SettingsConfigDict(env_prefix="CC_STT_", extra="ignore")

    engine: str = "auto"
    language: str = "en"
    wake_word: str = "hey_claude"
    mic_device: str = "default"
    auto_listen: bool = False
    strip_fillers: bool = True
    intent_match: bool = True
    max_words: int = 200

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
        **kwargs: Any,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Priority: env vars > init (TOML values) > defaults."""
        return (env_settings, init_settings)


def load_stt_config() -> STTConfig:
    """Load STT config from [stt] section of .cc-senses.toml with env var overrides."""
    return STTConfig(**load_toml_section("stt"))
