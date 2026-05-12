"""Configuration loading from .cc-senses.toml [vlm] section and environment variables."""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from cc_voice_common.config import load_toml_section


class VLMConfig(BaseSettings):
    """VLM plugin configuration for the llama-cpp-python in-process engine."""

    model_config = SettingsConfigDict(env_prefix="CC_VLM_", extra="ignore")

    engine: str = "auto"
    model_path: str = ""
    mmproj_path: str = ""
    handler_name: str = "moondream"
    n_ctx: int = 4096
    n_gpu_layers: int = 0
    max_tokens: int = 256
    max_dimension: int = 768
    jpeg_quality: int = 85
    template: str = "generic"
    cache_size: int = 32

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


def load_vlm_config() -> VLMConfig:
    """Load VLM config from [vlm] section of .cc-senses.toml with env var overrides."""
    return VLMConfig(**load_toml_section("vlm"))
