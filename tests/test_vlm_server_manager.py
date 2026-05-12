"""Tests for cc_vlm.server_manager — llama-server lifecycle helpers.

Mocks httpx (for is_reachable and wait_for_ready), subprocess.Popen (for
spawn), and os.kill (for pid_is_alive / shutdown). PID_FILE and LOG_FILE
are monkeypatched into tmp_path so tests don't touch ~/.cache.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cc_vlm import server_manager


@pytest.fixture
def isolated_pidfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PID_FILE and LOG_FILE at tmp_path so tests don't touch ~/.cache."""
    pid_file = tmp_path / "llama-server.pid"
    log_file = tmp_path / "llama-server.log"
    monkeypatch.setattr(server_manager, "PID_FILE", pid_file)
    monkeypatch.setattr(server_manager, "LOG_FILE", log_file)
    return pid_file


@pytest.fixture
def mock_httpx() -> MagicMock:
    """Install a fake httpx into sys.modules for server_manager to import.

    Tests configure `.get.return_value.status_code` or `.get.side_effect`
    to drive is_reachable behavior.
    """
    fake = MagicMock()

    class FakeConnectError(Exception):
        pass

    class FakeTimeoutError(Exception):
        pass

    fake.ConnectError = FakeConnectError
    fake.TimeoutException = FakeTimeoutError

    default_response = MagicMock()
    default_response.status_code = 200
    fake.get.return_value = default_response

    saved = sys.modules.get("httpx")
    sys.modules["httpx"] = fake
    yield fake
    if saved is None:
        sys.modules.pop("httpx", None)
    else:
        sys.modules["httpx"] = saved


class TestIsReachable:
    def test_reachable_on_200(self, mock_httpx: MagicMock) -> None:
        assert server_manager.is_reachable("http://localhost:8080") is True
        mock_httpx.get.assert_called_once()
        called_url = mock_httpx.get.call_args.args[0]
        assert called_url == "http://localhost:8080/health"

    def test_strips_trailing_slash(self, mock_httpx: MagicMock) -> None:
        server_manager.is_reachable("http://localhost:8080/")
        called_url = mock_httpx.get.call_args.args[0]
        assert called_url == "http://localhost:8080/health"

    def test_unreachable_on_503(self, mock_httpx: MagicMock) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        assert server_manager.is_reachable("http://localhost:8080") is False

    def test_unreachable_on_connect_error(self, mock_httpx: MagicMock) -> None:
        mock_httpx.get.side_effect = mock_httpx.ConnectError("refused")
        assert server_manager.is_reachable("http://localhost:8080") is False

    def test_unreachable_on_timeout(self, mock_httpx: MagicMock) -> None:
        mock_httpx.get.side_effect = mock_httpx.TimeoutException("timeout")
        assert server_manager.is_reachable("http://localhost:8080") is False

    def test_unreachable_when_httpx_missing(self) -> None:
        saved = sys.modules.pop("httpx", None)
        sys.modules["httpx"] = None  # type: ignore[assignment]
        try:
            assert server_manager.is_reachable("http://localhost:8080") is False
        finally:
            sys.modules.pop("httpx", None)
            if saved is not None:
                sys.modules["httpx"] = saved


class TestIsLocalhost:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8080",
            "http://localhost",
            "http://127.0.0.1:8080",
            "http://127.0.0.1",
            "http://[::1]:8080",
            "https://LOCALHOST:8080",
        ],
    )
    def test_local_urls(self, url: str) -> None:
        assert server_manager.is_localhost(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com:8080",
            "http://192.168.1.5:8080",
            "http://10.0.0.1",
            "http://my-server.local",
        ],
    )
    def test_remote_urls(self, url: str) -> None:
        assert server_manager.is_localhost(url) is False


class TestPidfileLifecycle:
    def test_write_and_read(self, isolated_pidfile: Path) -> None:
        server_manager.write_pidfile(12345)
        assert isolated_pidfile.read_text() == "12345"
        assert server_manager.read_pidfile() == 12345

    def test_write_creates_parent_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        nested = tmp_path / "a" / "b" / "c" / "llama-server.pid"
        monkeypatch.setattr(server_manager, "PID_FILE", nested)
        server_manager.write_pidfile(99)
        assert nested.exists()

    def test_read_returns_none_when_missing(self, isolated_pidfile: Path) -> None:
        assert server_manager.read_pidfile() is None

    def test_read_returns_none_on_garbage(self, isolated_pidfile: Path) -> None:
        isolated_pidfile.parent.mkdir(parents=True, exist_ok=True)
        isolated_pidfile.write_text("not-a-number")
        assert server_manager.read_pidfile() is None

    def test_clear_removes_file(self, isolated_pidfile: Path) -> None:
        server_manager.write_pidfile(7)
        assert isolated_pidfile.exists()
        server_manager.clear_pidfile()
        assert not isolated_pidfile.exists()

    def test_clear_is_idempotent(self, isolated_pidfile: Path) -> None:
        # Pidfile doesn't exist — clear should not raise
        server_manager.clear_pidfile()
        server_manager.clear_pidfile()  # second call also fine


class TestPidIsAlive:
    def test_returns_true_when_kill_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "kill", lambda pid, sig: None)
        assert server_manager.pid_is_alive(12345) is True

    def test_returns_false_on_process_lookup_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_lookup(pid: int, sig: int) -> None:
            raise ProcessLookupError()

        monkeypatch.setattr(os, "kill", raise_lookup)
        assert server_manager.pid_is_alive(12345) is False

    def test_returns_true_on_permission_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PermissionError means process exists but we can't signal it (different user).
        Treat as alive — the server still occupies the port."""

        def raise_perm(pid: int, sig: int) -> None:
            raise PermissionError()

        monkeypatch.setattr(os, "kill", raise_perm)
        assert server_manager.pid_is_alive(12345) is True


class TestSpawn:
    def test_spawn_invokes_popen_with_expected_args(
        self,
        isolated_pidfile: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        recorded: dict[str, object] = {}

        class FakeProc:
            pid = 99999

        def fake_popen(*args: object, **kwargs: object) -> FakeProc:
            recorded["args"] = args
            recorded["kwargs"] = kwargs
            return FakeProc()

        monkeypatch.setattr(server_manager.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(server_manager.shutil, "which", lambda _name: "/usr/bin/llama-server")

        pid = server_manager.spawn(
            model_path="/m/model.gguf",
            mmproj_path="/m/mmproj.gguf",
            port=8080,
            binary="llama-server",
        )

        assert pid == 99999
        cmd = recorded["args"][0]
        assert cmd == [
            "llama-server",
            "-m",
            "/m/model.gguf",
            "--mmproj",
            "/m/mmproj.gguf",
            "--port",
            "8080",
        ]
        kwargs = recorded["kwargs"]
        assert kwargs["start_new_session"] is True
        assert kwargs["stderr"] == server_manager.subprocess.STDOUT

    def test_spawn_writes_pidfile(
        self,
        isolated_pidfile: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeProc:
            pid = 42

        monkeypatch.setattr(server_manager.subprocess, "Popen", lambda *a, **kw: FakeProc())
        monkeypatch.setattr(server_manager.shutil, "which", lambda _name: "/bin/llama-server")

        server_manager.spawn("/m.gguf", "/mm.gguf", 8080, "llama-server")

        assert isolated_pidfile.read_text() == "42"

    def test_spawn_raises_when_binary_missing(
        self,
        isolated_pidfile: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(server_manager.shutil, "which", lambda _name: None)

        with pytest.raises(FileNotFoundError, match="llama-server"):
            server_manager.spawn("/m.gguf", "/mm.gguf", 8080, "llama-server")


class TestWaitForReady:
    def test_returns_true_when_immediately_reachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: True)
        assert server_manager.wait_for_ready("http://localhost:8080", timeout=5.0) is True

    def test_returns_true_after_polling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_reachable(url: str, timeout: float = 2.0) -> bool:
            calls["n"] += 1
            return calls["n"] >= 3  # 200 on the third call

        monkeypatch.setattr(server_manager, "is_reachable", fake_reachable)
        # Use a very short interval so the test stays fast
        result = server_manager.wait_for_ready("http://localhost:8080", timeout=2.0, interval=0.01)
        assert result is True
        assert calls["n"] == 3

    def test_returns_false_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: False)
        result = server_manager.wait_for_ready("http://localhost:8080", timeout=0.1, interval=0.05)
        assert result is False


class TestEnsureRunning:
    def test_returns_true_when_already_reachable(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: True)
        spawn_calls = {"n": 0}
        monkeypatch.setattr(
            server_manager,
            "spawn",
            lambda *a, **kw: spawn_calls.update(n=spawn_calls["n"] + 1) or 1,
        )

        result = server_manager.ensure_running(
            "http://localhost:8080", 8080, "llama-server", "/m.gguf", "/mm.gguf"
        )

        assert result is True
        assert spawn_calls["n"] == 0  # didn't spawn

    def test_skips_spawn_when_pidfile_alive_and_reachable(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server_manager.write_pidfile(12345)
        # First is_reachable call (line 1) returns False; subsequent True (after pidfile check)
        call_count = {"n": 0}

        def reachable(url: str, timeout: float = 2.0) -> bool:
            call_count["n"] += 1
            return call_count["n"] >= 2

        monkeypatch.setattr(server_manager, "is_reachable", reachable)
        monkeypatch.setattr(server_manager, "pid_is_alive", lambda pid: True)
        spawn_calls = {"n": 0}
        monkeypatch.setattr(
            server_manager,
            "spawn",
            lambda *a, **kw: spawn_calls.update(n=spawn_calls["n"] + 1) or 1,
        )

        result = server_manager.ensure_running(
            "http://localhost:8080", 8080, "llama-server", "/m.gguf", "/mm.gguf"
        )

        assert result is True
        assert spawn_calls["n"] == 0

    def test_spawns_when_pidfile_dead(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server_manager.write_pidfile(99999)
        monkeypatch.setattr(server_manager, "pid_is_alive", lambda pid: False)

        # is_reachable: False (initial), True (after spawn)
        call_count = {"n": 0}

        def reachable(url: str, timeout: float = 2.0) -> bool:
            call_count["n"] += 1
            return call_count["n"] >= 2

        monkeypatch.setattr(server_manager, "is_reachable", reachable)
        spawn_calls = {"n": 0}
        monkeypatch.setattr(
            server_manager,
            "spawn",
            lambda *a, **kw: spawn_calls.update(n=spawn_calls["n"] + 1) or 7,
        )
        monkeypatch.setattr(server_manager, "wait_for_ready", lambda url, **kw: True)

        result = server_manager.ensure_running(
            "http://localhost:8080", 8080, "llama-server", "/m.gguf", "/mm.gguf"
        )

        assert result is True
        assert spawn_calls["n"] == 1

    def test_spawns_when_nothing_present(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: False)
        spawn_calls = {"n": 0}
        monkeypatch.setattr(
            server_manager,
            "spawn",
            lambda *a, **kw: spawn_calls.update(n=spawn_calls["n"] + 1) or 7,
        )
        monkeypatch.setattr(server_manager, "wait_for_ready", lambda url, **kw: True)

        result = server_manager.ensure_running(
            "http://localhost:8080", 8080, "llama-server", "/m.gguf", "/mm.gguf"
        )

        assert result is True
        assert spawn_calls["n"] == 1

    def test_no_spawn_when_remote_url(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: False)
        spawn_calls = {"n": 0}
        monkeypatch.setattr(
            server_manager,
            "spawn",
            lambda *a, **kw: spawn_calls.update(n=spawn_calls["n"] + 1) or 0,
        )

        result = server_manager.ensure_running(
            "http://example.com:8080", 8080, "llama-server", "/m.gguf", "/mm.gguf"
        )

        assert result is False
        assert spawn_calls["n"] == 0

    def test_no_spawn_when_paths_missing(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: False)
        spawn_calls = {"n": 0}
        monkeypatch.setattr(
            server_manager,
            "spawn",
            lambda *a, **kw: spawn_calls.update(n=spawn_calls["n"] + 1) or 0,
        )

        result = server_manager.ensure_running(
            "http://localhost:8080", 8080, "llama-server", "", ""
        )

        assert result is False
        assert spawn_calls["n"] == 0

    def test_returns_false_when_binary_missing(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server_manager, "is_reachable", lambda url, timeout=2.0: False)

        def raise_fnf(*args: object, **kwargs: object) -> int:
            raise FileNotFoundError("llama-server")

        monkeypatch.setattr(server_manager, "spawn", raise_fnf)

        result = server_manager.ensure_running(
            "http://localhost:8080", 8080, "llama-server", "/m.gguf", "/mm.gguf"
        )

        assert result is False


class TestShutdown:
    def test_sends_sigterm_when_alive(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server_manager.write_pidfile(54321)
        monkeypatch.setattr(server_manager, "pid_is_alive", lambda pid: True)
        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append((pid, sig)))

        server_manager.shutdown(only_if_ours=True)

        assert signals == [(54321, signal.SIGTERM)]
        assert not isolated_pidfile.exists()

    def test_clears_pidfile_when_dead(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server_manager.write_pidfile(11111)
        monkeypatch.setattr(server_manager, "pid_is_alive", lambda pid: False)
        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append((pid, sig)))

        server_manager.shutdown(only_if_ours=True)

        assert signals == []  # didn't try to signal a dead pid
        assert not isolated_pidfile.exists()

    def test_noop_when_pidfile_absent(
        self, isolated_pidfile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append((pid, sig)))

        server_manager.shutdown(only_if_ours=True)

        assert signals == []
