"""Shared config utilities — TOML discovery and section loading for cc-senses-bridge plugins."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILENAMES = [".cc-senses.toml"]


def find_config_file() -> Path | None:
    """Walk up from cwd to find .cc-senses.toml."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        for filename in CONFIG_FILENAMES:
            candidate = directory / filename
            if candidate.is_file():
                return candidate
    return None


def load_toml_section(section: str) -> dict[str, Any]:
    """Load a section from .cc-senses.toml, returning {} if not found."""
    config_file = find_config_file()
    if config_file is None:
        return {}
    with config_file.open("rb") as f:
        data = tomllib.load(f)
    return dict(data.get(section, {}))
