"""SessionEnd hook: stop the cc-senses-bridge-spawned llama-server.

Registered as a Claude Code SessionEnd hook in hooks/hooks.json. Fires
once when the CC session ends. Calls `server_manager.shutdown` with
`only_if_ours=True` — silently no-ops when there's no pidfile (user is
managing the daemon themselves or no preload/lazy spawn ever fired).

Wraps the call in a broad except so a failure here never leaks noise
into CC's shutdown path.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

_LOG_PATH = Path.home() / ".cache" / "cc-senses-bridge" / "shutdown.log"


def _debug(msg: str) -> None:
    """Append to debug log if CC_VLM_HOOK_DEBUG=1, else no-op."""
    if os.environ.get("CC_VLM_HOOK_DEBUG") != "1":
        return
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a") as f:
        f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}\n")


def main() -> None:
    """SessionEnd entry point. SIGTERMs the spawned llama-server if any."""
    _debug("shutdown hook fired")
    try:
        from cc_vlm import server_manager

        server_manager.shutdown(only_if_ours=True)
    except Exception as exc:  # noqa: BLE001
        # Reason: SessionEnd hooks should never raise — CC has nothing
        # useful to do with the error and stderr from a hook can pollute
        # session-shutdown logs. Best-effort cleanup is the right model.
        _debug(f"shutdown failed: {exc}")


if __name__ == "__main__":
    main()
