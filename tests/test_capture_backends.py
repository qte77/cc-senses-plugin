"""Tests for cc_vlm.capture backend selection + native backends (#119).

subprocess, platform and PATH lookups are mocked; native backends are
round-tripped through a real PNG written by the fake subprocess.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from cc_vlm import capture
from cc_vlm.capture import ScreenCapture, auto_candidates, select_backends
from cc_vlm.config import VLMConfig

# --- detection matrix ---


@pytest.mark.parametrize(
    ("system", "session", "desktop", "expected"),
    [
        ("Darwin", "", "", ["screencapture", "mss"]),
        ("Linux", "wayland", "GNOME", ["flameshot", "gnome-screenshot", "mss"]),
        ("Linux", "wayland", "ubuntu:GNOME", ["flameshot", "gnome-screenshot", "mss"]),
        ("Linux", "wayland", "KDE", ["spectacle", "flameshot", "mss"]),
        ("Linux", "wayland", "sway", ["grim", "flameshot", "mss"]),
        ("Linux", "wayland", "Hyprland", ["grim", "flameshot", "mss"]),
        ("Linux", "x11", "XFCE", ["scrot", "flameshot", "gnome-screenshot", "mss"]),
        ("Linux", "tty", "", ["mss"]),
        ("Linux", "wayland", "weston", ["mss"]),
        ("Windows", "", "", ["mss"]),
    ],
)
def test_auto_candidates_matrix(
    system: str, session: str, desktop: str, expected: list[str]
) -> None:
    assert auto_candidates(system, session, desktop) == expected


@pytest.fixture
def gnome_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")


@pytest.mark.usefixtures("gnome_wayland")
class TestSelectBackends:
    def test_auto_skips_tools_not_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        on_path = {"gnome-screenshot"}
        monkeypatch.setattr(capture.shutil, "which", lambda n: n if n in on_path else None)
        assert select_backends("auto") == ["gnome-screenshot", "mss"]

    def test_override_wins_over_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(capture.shutil, "which", lambda n: f"/usr/bin/{n}")
        assert select_backends("scrot") == ["scrot"]

    def test_override_missing_tool_fails_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(capture.shutil, "which", lambda _n: None)
        with pytest.raises(RuntimeError, match="grim.*not on PATH"):
            select_backends("grim")

    def test_override_mss_needs_no_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(capture.shutil, "which", lambda _n: None)
        assert select_backends("mss") == ["mss"]

    def test_unknown_override_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown capture backend"):
            select_backends("paint")


def test_config_field_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert VLMConfig().capture_backend == "auto"
    monkeypatch.setenv("CC_VLM_CAPTURE_BACKEND", "grim")
    assert VLMConfig().capture_backend == "grim"


# --- native backend invocations ---


def _fake_run_writing_png(calls: list[list[str]]) -> Any:
    """subprocess.run stand-in: records argv, writes a 4x3 PNG where the tool would."""

    def run(argv: list[str], **_kwargs: Any) -> MagicMock:
        calls.append(argv)
        if argv[0] == "flameshot":
            out = Path(argv[argv.index("-p") + 1]) / "screenshot_2026.png"
        else:
            out = Path(argv[-1])
        Image.new("RGBA", (4, 3), (255, 0, 0, 255)).save(out)
        return MagicMock(returncode=0)

    return run


@pytest.mark.parametrize(
    ("backend", "argv_head"),
    [
        ("screencapture", ["screencapture", "-x", "-t", "png"]),
        ("grim", ["grim"]),
        ("gnome-screenshot", ["gnome-screenshot", "-f"]),
        ("spectacle", ["spectacle", "-b", "-n", "-o"]),
        ("scrot", ["scrot", "-o"]),
        ("flameshot", ["flameshot", "full", "-p"]),
    ],
)
def test_native_backend_round_trips_png(
    backend: str, argv_head: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capture.shutil, "which", lambda n: f"/usr/bin/{n}")
    calls: list[list[str]] = []
    with patch.object(capture.subprocess, "run", side_effect=_fake_run_writing_png(calls)):
        img = ScreenCapture(backend).grab()
    assert calls[0][: len(argv_head)] == argv_head
    assert img.mode == "RGB"
    assert img.size == (4, 3)


@pytest.mark.usefixtures("gnome_wayland")
def test_auto_falls_through_to_next_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture.shutil, "which", lambda n: f"/usr/bin/{n}")
    calls: list[list[str]] = []
    write_png = _fake_run_writing_png(calls)

    def run(argv: list[str], **kwargs: Any) -> MagicMock:
        if argv[0] == "flameshot":
            calls.append(argv)
            raise subprocess.CalledProcessError(1, argv)
        return write_png(argv, **kwargs)

    with patch.object(capture.subprocess, "run", side_effect=run):
        img = ScreenCapture().grab()
    assert [c[0] for c in calls] == ["flameshot", "gnome-screenshot"]
    assert img.size == (4, 3)


@pytest.mark.usefixtures("gnome_wayland")
def test_all_backends_failing_reports_each(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture.shutil, "which", lambda _n: None)
    with (
        patch("cc_vlm.capture.mss.mss", side_effect=RuntimeError("XGetImage() failed")),
        pytest.raises(RuntimeError, match=r"mss: XGetImage\(\) failed"),
    ):
        ScreenCapture().grab()


def test_override_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture.shutil, "which", lambda n: f"/usr/bin/{n}")
    error = subprocess.CalledProcessError(1, ["scrot"])
    with (
        patch.object(capture.subprocess, "run", side_effect=error),
        patch("cc_vlm.capture.mss.mss") as mss_cls,
        pytest.raises(RuntimeError, match="scrot"),
    ):
        ScreenCapture("scrot").grab()
    mss_cls.assert_not_called()
