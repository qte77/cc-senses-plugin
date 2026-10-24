"""Screen capture returning a PIL Image, via a native tool or python-mss.

Backend choice, first match wins:

1. Explicit override (`[vlm] capture_backend` / `CC_VLM_CAPTURE_BACKEND`) —
   used alone, never falls back; a missing tool fails loudly.
2. `auto` — a platform/session-specific list (see `auto_candidates`), skipping
   tools not on PATH, with `mss` as the last resort. A backend that fails at
   runtime falls through to the next one.

Native tools capture the primary/focused display and ignore `monitor`; only
`mss` honours the monitor index.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import mss
from PIL import Image

# Native backend name -> argv that writes a PNG to `out`.
_NATIVE: dict[str, Callable[[Path], list[str]]] = {
    "screencapture": lambda out: ["screencapture", "-x", "-t", "png", str(out)],
    "grim": lambda out: ["grim", str(out)],
    "gnome-screenshot": lambda out: ["gnome-screenshot", "-f", str(out)],
    "spectacle": lambda out: ["spectacle", "-b", "-n", "-o", str(out)],
    "scrot": lambda out: ["scrot", "-o", str(out)],
    # flameshot's -p takes a directory and picks its own file name.
    "flameshot": lambda out: ["flameshot", "full", "-p", str(out.parent)],
}
BACKENDS = (*_NATIVE, "mss")
_TIMEOUT_S = 30


def auto_candidates(system: str, session: str, desktop: str) -> list[str]:
    """Backends to probe, in order, for a platform / XDG session / desktop."""
    desktop = desktop.lower()
    if system == "Darwin":
        return ["screencapture", "mss"]
    if system == "Linux" and session == "wayland":
        if "gnome" in desktop:
            return ["flameshot", "gnome-screenshot", "mss"]
        if "kde" in desktop:
            return ["spectacle", "flameshot", "mss"]
        if "sway" in desktop or "hyprland" in desktop:
            return ["grim", "flameshot", "mss"]
    if system == "Linux" and session == "x11":
        return ["scrot", "flameshot", "gnome-screenshot", "mss"]
    return ["mss"]


def select_backends(override: str) -> list[str]:
    """Resolve the backend(s) to try for an override value or `auto`."""
    if override != "auto":
        if override not in BACKENDS:
            raise ValueError(
                f"Unknown capture backend {override!r}. Use auto or one of: {', '.join(BACKENDS)}"
            )
        if override != "mss" and shutil.which(override) is None:
            raise RuntimeError(f"capture_backend={override!r} but {override} is not on PATH")
        return [override]
    candidates = auto_candidates(
        platform.system(),
        os.environ.get("XDG_SESSION_TYPE", ""),
        os.environ.get("XDG_CURRENT_DESKTOP", ""),
    )
    return [b for b in candidates if b == "mss" or shutil.which(b) is not None]


def _grab_native(name: str) -> Image.Image:
    with tempfile.TemporaryDirectory(prefix="cc_vlm_capture_") as tmp:
        out = Path(tmp) / "capture.png"
        try:
            subprocess.run(  # noqa: S603 — fixed argv from _NATIVE, no shell
                _NATIVE[name](out), check=True, capture_output=True, timeout=_TIMEOUT_S
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace").strip() if exc.stderr else ""
            raise RuntimeError(f"exit {exc.returncode}: {stderr[:200]}") from exc
        written = out if out.exists() else next(Path(tmp).glob("*.png"), None)
        if written is None:
            raise RuntimeError(f"{name} exited 0 but wrote no PNG")
        with Image.open(written) as img:
            return img.convert("RGB")


def _grab_mss(monitor: int) -> Image.Image:
    # mss treats monitor 0 as the all-monitor composite; prefer the primary.
    with mss.mss() as sct:
        mon_index = monitor if monitor > 0 else 1
        if mon_index >= len(sct.monitors):
            mon_index = 1
        shot = sct.grab(sct.monitors[mon_index])
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class ScreenCapture:
    """Screen capture with pluggable native/mss backends."""

    def __init__(self, backend: str = "auto") -> None:
        self.backend = backend

    def grab(self, monitor: int = 0) -> Image.Image:
        """Grab a screenshot and return it as a PIL RGB Image.

        Args:
            monitor: mss only — 0 or out-of-range means the primary monitor,
                     1+ a specific monitor. Native tools ignore it.

        Raises:
            RuntimeError: every selected backend failed (message lists each).
        """
        errors: list[str] = []
        for name in select_backends(self.backend):
            try:
                return _grab_mss(monitor) if name == "mss" else _grab_native(name)
            except Exception as exc:  # noqa: BLE001 — collected and re-raised below
                errors.append(f"{name}: {exc}")
        raise RuntimeError("; ".join(errors) or "no capture backend available")
