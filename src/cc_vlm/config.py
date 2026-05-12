"""Configuration loading from .cc-senses.toml [vlm] section and environment variables."""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from cc_voice_common.config import load_toml_section


class VLMConfig(BaseSettings):
    """VLM plugin configuration.

    Covers both engines:
    - `LlamaCppVLMEngine` (in-process): `model_path` + `mmproj_path` +
      `handler_name` + `n_ctx`/`n_gpu_layers`/`max_tokens`.
    - `LlamaServerVLMEngine` (HTTP): `server_url` + `server_model_alias`
      + (Phase 2) `server_port`/`server_binary`/`auto_spawn` +
      (Phase 3) `preload`.

    `max_dimension`/`jpeg_quality`/`template`/`cache_size` apply to the
    capture+inference pipeline regardless of which engine is selected.
    """

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
    # llama-server HTTP backend (Phase 1 wires server_url + alias;
    # remaining fields are inert until Phase 2 lifecycle work lands).
    server_url: str = ""
    server_model_alias: str = ""
    server_port: int = 8080
    server_binary: str = "llama-server"
    auto_spawn: bool = True
    preload: bool = False

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
