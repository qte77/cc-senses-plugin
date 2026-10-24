"""Shared config utilities — TOML discovery and section loading for cc-senses-plugin plugins."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from pydantic import BaseModel, ValidationError

CONFIG_FILENAMES = [".cc-senses.toml"]
T = TypeVar("T", bound=BaseModel)


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


def _die(module_name: str, message: str) -> NoReturn:
    print(f"{module_name}: {message}", file=sys.stderr)
    sys.exit(1)


def load_toml_section_or_die(section: str, module_name: str) -> dict[str, Any]:
    """Like load_toml_section, but a bad config file exits 1 with one line."""
    try:
        return load_toml_section(section)
    except tomllib.TOMLDecodeError as exc:
        _die(
            module_name,
            f".cc-senses.toml: {exc}. Often a duplicate [section] or repeated key.",
        )
    except PermissionError as exc:
        _die(module_name, f"cannot read {exc.filename} (permission denied).")


def build_config_or_die(config_cls: type[T], section: str, module_name: str) -> T:
    """Load [section] and build config_cls; invalid values exit 1 with one line."""
    data = load_toml_section_or_die(section, module_name)
    try:
        return config_cls(**data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        _die(module_name, f"[{section}] config invalid — {problems}.")
