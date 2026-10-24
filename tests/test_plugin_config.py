"""Tests for plugin configuration validity — TDD RED phase.

Validates plugin.json and marketplace.json conform to Claude Code plugin
system requirements, catching discovery/resolution issues before install.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[\w.]+)?$")


# --- Fixtures ---


@pytest.fixture()
def plugin_data() -> dict[str, object]:
    return json.loads(PLUGIN_JSON.read_text())


@pytest.fixture()
def marketplace_data() -> dict[str, object]:
    return json.loads(MARKETPLACE_JSON.read_text())


# --- plugin.json schema ---


class TestPluginJsonSchema:
    def test_file_exists(self) -> None:
        assert PLUGIN_JSON.is_file(), f"{PLUGIN_JSON} must exist"

    def test_valid_json(self) -> None:
        data = json.loads(PLUGIN_JSON.read_text())
        assert isinstance(data, dict)

    def test_name_required(self, plugin_data: dict[str, object]) -> None:
        assert "name" in plugin_data, "plugin.json must have 'name' field"

    def test_name_kebab_case(self, plugin_data: dict[str, object]) -> None:
        name = plugin_data["name"]
        assert isinstance(name, str)
        assert KEBAB_CASE_RE.match(name), f"name '{name}' must be kebab-case"

    def test_version_semver(self, plugin_data: dict[str, object]) -> None:
        version = plugin_data.get("version", "")
        assert isinstance(version, str)
        assert SEMVER_RE.match(version), f"version '{version}' must be semver"

    def test_description_present(self, plugin_data: dict[str, object]) -> None:
        assert plugin_data.get("description"), "plugin.json should have description"


# --- marketplace.json schema ---


class TestMarketplaceJsonSchema:
    def test_file_exists(self) -> None:
        assert MARKETPLACE_JSON.is_file(), f"{MARKETPLACE_JSON} must exist"

    def test_valid_json(self) -> None:
        data = json.loads(MARKETPLACE_JSON.read_text())
        assert isinstance(data, dict)

    def test_name_required(self, marketplace_data: dict[str, object]) -> None:
        assert "name" in marketplace_data

    def test_owner_required(self, marketplace_data: dict[str, object]) -> None:
        owner = marketplace_data.get("owner")
        assert isinstance(owner, dict)
        assert "name" in owner

    def test_plugins_array(self, marketplace_data: dict[str, object]) -> None:
        plugins = marketplace_data.get("plugins")
        assert isinstance(plugins, list)
        assert len(plugins) > 0, "marketplace must list at least one plugin"


# --- Plugin entries ---


class TestMarketplacePluginEntries:
    def test_each_plugin_has_name_and_source(self, marketplace_data: dict[str, object]) -> None:
        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            assert "name" in entry, f"plugin entry missing 'name': {entry}"
            assert "source" in entry, f"plugin entry missing 'source': {entry}"

    def test_plugin_names_kebab_case(self, marketplace_data: dict[str, object]) -> None:
        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            name = entry["name"]
            assert KEBAB_CASE_RE.match(name), f"plugin name '{name}' must be kebab-case"

    def test_no_duplicate_plugin_names(self, marketplace_data: dict[str, object]) -> None:
        names = [e["name"] for e in marketplace_data["plugins"]]  # type: ignore[union-attr]
        assert len(names) == len(set(names)), f"duplicate plugin names: {names}"


# --- Source resolution ---


class TestPluginSourceResolution:
    """Verify plugin sources resolve to valid plugin directories."""

    def test_relative_source_resolves(self, marketplace_data: dict[str, object]) -> None:
        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            source = entry["source"]
            if isinstance(source, str) and source.startswith("./"):
                resolved = REPO_ROOT / source
                assert resolved.is_dir(), (
                    f"relative source '{source}' does not resolve to a directory"
                )

    def test_relative_source_has_plugin_json(self, marketplace_data: dict[str, object]) -> None:
        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            source = entry["source"]
            if isinstance(source, str) and source.startswith("./"):
                plugin_json = REPO_ROOT / source / ".claude-plugin" / "plugin.json"
                assert plugin_json.is_file(), (
                    f"relative source '{source}' missing .claude-plugin/plugin.json"
                )

    def test_relative_source_not_git_submodule(self, marketplace_data: dict[str, object]) -> None:
        """Git submodules are NOT initialized during CC marketplace clone.

        If a plugin source is a relative path to a git submodule, the
        directory will be empty after clone and CC reports 'plugin not found'.
        Use a github/url source type instead.
        """
        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            source = entry["source"]
            if isinstance(source, str) and source.startswith("./"):
                git_file = REPO_ROOT / source / ".git"
                # .git as a FILE (not dir) = submodule reference
                assert not git_file.is_file(), (
                    f"source '{source}' is a git submodule — CC won't resolve it. "
                    f"Use {{'source': 'github', 'repo': '...'}} instead."
                )

    def test_self_referential_source_resolves(self, marketplace_data: dict[str, object]) -> None:
        """Source './' means the repo root IS the plugin."""
        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            source = entry["source"]
            if source == "./":
                assert PLUGIN_JSON.is_file(), (
                    "self-referential source './' requires .claude-plugin/plugin.json at repo root"
                )


# --- Version consistency ---


class TestVersionConsistency:
    def test_plugin_version_matches_marketplace_entry(
        self,
        plugin_data: dict[str, object],
        marketplace_data: dict[str, object],
    ) -> None:
        """CC docs warn: plugin.json version wins silently over marketplace version.

        Keep them in sync to avoid confusion.
        """
        plugin_name = plugin_data["name"]
        plugin_version = plugin_data.get("version")
        if not plugin_version:
            return  # no version in plugin.json, marketplace is authoritative

        for entry in marketplace_data["plugins"]:  # type: ignore[union-attr]
            if entry["name"] == plugin_name:
                mp_version = entry.get("version")
                if mp_version:
                    assert plugin_version == mp_version, (
                        f"version mismatch: plugin.json={plugin_version} "
                        f"vs marketplace.json={mp_version}"
                    )
                break


# --- Plugin-root resolution (#106) ---

UV_PROJECT_PREFIX = 'uv run --project "${CLAUDE_PLUGIN_ROOT}" python -m cc_'
PYTHON_MODULE_RE = re.compile(r"^.*python -m cc_.*$", re.MULTILINE)


class TestCommandsResolveAgainstPluginRoot:
    """Hooks and skills run with the consumer's cwd; a bare `uv run` or `python`
    resolves the consumer's venv, which has no cc_* modules installed."""

    def test_hook_commands_pin_plugin_project(self) -> None:
        hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        commands = [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]
        assert commands
        for command in commands:
            assert command.startswith(UV_PROJECT_PREFIX), command

    @pytest.mark.parametrize("skill", ["speak", "listen", "see"])
    def test_skill_commands_pin_plugin_project(self, skill: str) -> None:
        text = (REPO_ROOT / "skills" / skill / "SKILL.md").read_text()
        runnable = [line.strip() for line in PYTHON_MODULE_RE.findall(text) if "`" not in line]
        assert runnable, f"no runnable python -m line in skills/{skill}/SKILL.md"
        for line in runnable:
            assert line.startswith(UV_PROJECT_PREFIX), line
