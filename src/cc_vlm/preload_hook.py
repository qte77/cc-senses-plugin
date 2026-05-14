"""SessionStart hook: lazily spawn llama-server in the background.

Registered as a Claude Code SessionStart hook in hooks/hooks.json. Fires
once per session. Reads `VLMConfig`; if `preload=False` (default), exits
immediately (~200 ms Python startup, no work). Otherwise dispatches a
detached subprocess that runs `server_manager.ensure_running` so the CC
session itself doesn't block on the 3-5 s model load.

Two-function design (mirrors the dispatch / runner split used by the
Stop hook):
- `main()` — synchronous dispatcher. Decides whether to trigger preload
  based on config. Always returns fast.
- `run_preload_sync()` — what the detached subprocess actually executes.
  Loads config and calls `ensure_running` directly.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path

from cc_vlm.config import load_vlm_config

_LOG_PATH = Path.home() / ".cache" / "cc-senses-plugin" / "preload.log"


def _debug(msg: str) -> None:
    """Append to debug log if CC_VLM_HOOK_DEBUG=1, else no-op."""
    if os.environ.get("CC_VLM_HOOK_DEBUG") != "1":
        return
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a") as f:
        f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}\n")


def main() -> None:
    """SessionStart entry point. Decides whether to dispatch the preload runner."""
    _debug("preload hook fired")
    try:
        config = load_vlm_config()
    except Exception as exc:  # noqa: BLE001
        # Reason: pydantic-settings or VLM deps may not be installed for
        # team members who don't use /see. Silent no-op is the right
        # failure mode — never block CC session startup.
        _debug(f"config error: {exc}")
        return

    if not config.preload:
        _debug("preload disabled")
        return
    if not config.model_path or not config.mmproj_path:
        _debug("preload skipped: model_path or mmproj_path empty")
        return

    # Re-invoke ourselves in a detached subprocess so SessionStart doesn't
    # block on the up-to-30 s model load. start_new_session=True creates
    # an independent process group that survives this hook exiting.
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from cc_vlm.preload_hook import run_preload_sync; run_preload_sync()",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _debug(f"detached preload runner pid={proc.pid}")
    except OSError as exc:
        _debug(f"Popen failed: {exc}")


def run_preload_sync() -> None:
    """Detached runner — loads config and ensures the server is up.

    Blocks until llama-server's /health responds 200 (up to ~30 s).
    Called only via the subprocess dispatch in main() — not invoked by
    the hook synchronously.
    """
    try:
        config = load_vlm_config()
    except Exception:  # noqa: BLE001
        return
    if not config.model_path or not config.mmproj_path:
        return

    from cc_vlm import server_manager

    server_manager.ensure_running(
        config.server_url,
        config.server_port,
        config.server_binary,
        config.model_path,
        config.mmproj_path,
    )


if __name__ == "__main__":
    main()
