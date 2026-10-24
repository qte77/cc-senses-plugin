"""Bad .cc-senses.toml → one-line error + exit 1 from every load_*_config (#120)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cc_stt.config import load_stt_config
from cc_tts.config import load_config
from cc_vlm.config import load_vlm_config

# (module name, section, loader, a field value pydantic rejects)
MODULES: list[tuple[str, str, Callable[[], Any], str]] = [
    ("cc_tts", "tts", load_config, 'speed = "fast"'),
    ("cc_stt", "stt", load_stt_config, 'max_words = "many"'),
    ("cc_vlm", "vlm", load_vlm_config, 'n_ctx = "big"'),
]
IDS = [m[0] for m in MODULES]


def _write_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / ".cc-senses.toml"
    config.write_text(body)
    return config


def _exit_line(loader: Callable[[], Any], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exc_info:
        loader()
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    return lines[0]


@pytest.mark.parametrize(("module", "section", "loader", "bad_value"), MODULES, ids=IDS)
def test_malformed_toml(
    module: str,
    section: str,
    loader: Callable[[], Any],
    bad_value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path, monkeypatch, f"[{section}]\na = 1\n[{section}]\nb = 2\n")
    line = _exit_line(loader, capsys)
    assert line.startswith(f"{module}: .cc-senses.toml: ")
    assert "duplicate [section] or repeated key" in line


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
@pytest.mark.parametrize(("module", "section", "loader", "bad_value"), MODULES, ids=IDS)
def test_permission_denied(
    module: str,
    section: str,
    loader: Callable[[], Any],
    bad_value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _write_config(tmp_path, monkeypatch, f"[{section}]\n")
    config.chmod(0)
    try:
        line = _exit_line(loader, capsys)
    finally:
        config.chmod(0o600)
    assert line.startswith(f"{module}: cannot read ")
    assert "permission denied" in line


@pytest.mark.parametrize(("module", "section", "loader", "bad_value"), MODULES, ids=IDS)
def test_pydantic_validation_failure(
    module: str,
    section: str,
    loader: Callable[[], Any],
    bad_value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path, monkeypatch, f"[{section}]\n{bad_value}\n")
    field = bad_value.split(" = ")[0]
    line = _exit_line(loader, capsys)
    assert line.startswith(f"{module}: [{section}] config invalid — {field}: ")


def test_stt_hook_stays_silent_on_bad_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks must never block Claude Code, even when the config loader exits."""
    from cc_stt.hook_handler import should_auto_listen

    _write_config(tmp_path, monkeypatch, "[stt]\na = 1\n[stt]\n")
    assert should_auto_listen() is False
