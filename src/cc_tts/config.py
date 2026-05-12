"""Configuration loading from .cc-senses.toml [tts] section and environment variables."""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from cc_voice_common.config import load_toml_section


class TTSConfig(BaseSettings):
    """TTS plugin configuration."""

    model_config = SettingsConfigDict(env_prefix="CC_TTS_", extra="ignore")

    engine: str = "auto"
    voice: str = "en_US-amy-medium"
    speed: float = 1.0
    auto_read: bool = False
    max_chars: int = 2000
    player: str = "auto"

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


def load_config() -> TTSConfig:
    """Load config from .cc-senses.toml [tts] section with env var overrides."""
    return TTSConfig(**load_toml_section("tts"))
