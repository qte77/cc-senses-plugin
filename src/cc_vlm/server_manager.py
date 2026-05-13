"""Lifecycle helpers for the llama-server HTTP backend.

Owns spawn / pidfile / health-probe / shutdown for the local `llama-server`
process that `LlamaServerVLMEngine` talks to. Engine imports this module
as an opaque utility — there's no engine import here, so no circular risk.

Concurrency posture: best-effort, not locked. If two `/see` invocations
race during cold start, one binds the port and the other exits on
EADDRINUSE. The pidfile may transiently point at the dead PID; the next
invocation's `pid_is_alive` check self-heals.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

PID_FILE = Path.home() / ".cache" / "cc-senses-bridge" / "llama-server.pid"
LOG_FILE = Path.home() / ".cache" / "cc-senses-bridge" / "llama-server.log"

_LOCALHOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_reachable(url: str, timeout: float = 2.0) -> bool:
    """GET <url>/health → True on 200; False on any other status, transport
    error, missing httpx, or timeout."""
    try:
        import httpx
    except ImportError:
        return False
    try:
        response = httpx.get(f"{url.rstrip('/')}/health", timeout=timeout)
    except Exception:  # noqa: BLE001
        # Reason: httpx raises ConnectError, TimeoutException, ReadTimeout
        # and friends. All mean "not reachable" — catch broadly.
        return False
    return response.status_code == 200


def is_localhost(url: str) -> bool:
    """True iff the URL's host is loopback (localhost / 127.0.0.1 / ::1)."""
    host = (urlparse(url).hostname or "").lower()
    return host in _LOCALHOSTS


def read_pidfile() -> int | None:
    """Return the stored PID, or None if pidfile is absent / malformed."""
    try:
        return int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def write_pidfile(pid: int) -> None:
    """Persist PID to disk. Creates parent dirs."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def clear_pidfile() -> None:
    """Remove pidfile if present. Idempotent."""
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def pid_is_alive(pid: int) -> bool:
    """True iff a process with `pid` exists and we can probe it.

    `os.kill(pid, 0)` is the POSIX trick — sends no signal but raises
    ProcessLookupError if the pid is gone. PermissionError means the
    process exists under a different user (treat as alive — port still
    occupied).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def spawn(model_path: str, mmproj_path: str, port: int, binary: str) -> int:
    """Spawn `llama-server` as a detached background process.

    Writes pidfile and returns the spawned PID. Truncates LOG_FILE on
    each spawn so the log reflects only the most recent run.
    Raises FileNotFoundError if `binary` is not on PATH.
    """
    if shutil.which(binary) is None:
        msg = f"llama-server binary not found on PATH: {binary!r}"
        raise FileNotFoundError(msg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = LOG_FILE.open("wb")  # noqa: SIM115  (lifetime managed by child process)
    proc = subprocess.Popen(
        [binary, "-m", model_path, "--mmproj", mmproj_path, "--port", str(port)],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    write_pidfile(proc.pid)
    return proc.pid


def wait_for_ready(url: str, timeout: float = 30.0, interval: float = 0.5) -> bool:
    """Poll `/health` until 200 or timeout. Returns True on success."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_reachable(url, timeout=1.0):
            return True
        time.sleep(interval)
    return False


def ensure_running(
    server_url: str,
    server_port: int,
    server_binary: str,
    model_path: str,
    mmproj_path: str,
) -> bool:
    """Idempotent: ensure a llama-server is reachable on `server_url`.

    Order:
      1. probe /health → True if already up (user-managed or our prior spawn)
      2. if pidfile + alive + reachable → True (re-discovery on same session)
      3. refuse to spawn remote hosts
      4. refuse to spawn without model + mmproj paths
      5. spawn + wait_for_ready
    """
    if is_reachable(server_url):
        return True
    existing_pid = read_pidfile()
    if existing_pid is not None and pid_is_alive(existing_pid) and is_reachable(server_url):
        return True
    if not is_localhost(server_url):
        return False
    if not model_path or not mmproj_path:
        return False
    try:
        spawn(model_path, mmproj_path, server_port, server_binary)
    except FileNotFoundError:
        return False
    return wait_for_ready(server_url)


def shutdown(only_if_ours: bool = True) -> None:
    """SIGTERM the pidfile's process if alive; clear pidfile either way.

    When `only_if_ours=True` (default), absence of the pidfile means
    external management — silently no-op. Setting it to False is reserved
    for future "best-effort kill anything on the port" semantics; not used
    today.
    """
    _ = only_if_ours  # currently no-different branch; reserved for future use
    pid = read_pidfile()
    if pid is None:
        return
    if pid_is_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    clear_pidfile()
