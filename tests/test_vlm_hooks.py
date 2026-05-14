"""Tests for SessionStart preload hook + SessionEnd shutdown hook.

Pattern: each hook splits into a foreground dispatcher (decides whether to
trigger) and a background runner (actually loads the model). The dispatcher
runs synchronously during the CC SessionStart hook; the runner runs in a
detached subprocess so the session doesn't block on the ~3-5 s model load.

Tests cover both halves independently — Popen is mocked at the dispatch
boundary; ensure_running / shutdown are mocked at the runner boundary.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from cc_vlm import preload_hook, shutdown_hook
from cc_vlm.config import VLMConfig


@pytest.fixture
def captured_popen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    """Capture subprocess.Popen invocations from the hook dispatchers."""
    calls: list[tuple[Any, Any]] = []

    def fake_popen(*args: object, **kwargs: object) -> MagicMock:
        calls.append((args, kwargs))
        proc = MagicMock()
        proc.pid = 99
        return proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    return calls


class TestPreloadHookDispatcher:
    """`preload_hook.main()` decides whether to dispatch a detached runner."""

    def test_no_dispatch_when_preload_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        captured_popen: list[tuple[Any, Any]],
    ) -> None:
        cfg = VLMConfig(
            preload=False,
            model_path="/m.gguf",
            mmproj_path="/mm.gguf",
        )
        monkeypatch.setattr(preload_hook, "load_vlm_config", lambda: cfg)

        preload_hook.main()

        assert captured_popen == []

    def test_dispatches_when_preload_and_paths_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
        captured_popen: list[tuple[Any, Any]],
    ) -> None:
        cfg = VLMConfig(
            preload=True,
            model_path="/m.gguf",
            mmproj_path="/mm.gguf",
        )
        monkeypatch.setattr(preload_hook, "load_vlm_config", lambda: cfg)

        preload_hook.main()

        assert len(captured_popen) == 1
        _, kwargs = captured_popen[0]
        # Detached subprocess with new session — survives hook exit
        assert kwargs.get("start_new_session") is True

    def test_no_dispatch_when_model_path_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        captured_popen: list[tuple[Any, Any]],
    ) -> None:
        cfg = VLMConfig(preload=True, model_path="", mmproj_path="/mm.gguf")
        monkeypatch.setattr(preload_hook, "load_vlm_config", lambda: cfg)

        preload_hook.main()

        assert captured_popen == []

    def test_no_dispatch_when_mmproj_path_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        captured_popen: list[tuple[Any, Any]],
    ) -> None:
        cfg = VLMConfig(preload=True, model_path="/m.gguf", mmproj_path="")
        monkeypatch.setattr(preload_hook, "load_vlm_config", lambda: cfg)

        preload_hook.main()

        assert captured_popen == []

    def test_no_dispatch_when_config_load_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        captured_popen: list[tuple[Any, Any]],
    ) -> None:
        """Missing deps shouldn't crash a CC session startup — silently skip."""

        def raise_(*_a: object, **_kw: object) -> VLMConfig:
            raise RuntimeError("pydantic-settings not installed")

        monkeypatch.setattr(preload_hook, "load_vlm_config", raise_)

        preload_hook.main()  # must not raise

        assert captured_popen == []


class TestPreloadHookRunner:
    """`preload_hook.run_preload_sync()` is what the detached subprocess calls."""

    def test_calls_ensure_running_with_config_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = VLMConfig(
            preload=True,
            model_path="/m.gguf",
            mmproj_path="/mm.gguf",
            server_url="http://localhost:8080",
            server_port=8080,
            server_binary="llama-server",
        )
        monkeypatch.setattr(preload_hook, "load_vlm_config", lambda: cfg)

        calls: list[tuple[Any, ...]] = []

        def fake_ensure(*args: Any, **_kw: Any) -> bool:
            calls.append(args)
            return True

        from cc_vlm import server_manager

        monkeypatch.setattr(server_manager, "ensure_running", fake_ensure)

        preload_hook.run_preload_sync()

        assert len(calls) == 1
        # Positional args order: server_url, server_port, server_binary, model_path, mmproj_path
        assert calls[0] == (
            "http://localhost:8080",
            8080,
            "llama-server",
            "/m.gguf",
            "/mm.gguf",
        )

    def test_runner_noop_when_paths_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Defense-in-depth: even if dispatch happens with bad config, runner declines."""
        cfg = VLMConfig(preload=True, model_path="", mmproj_path="")
        monkeypatch.setattr(preload_hook, "load_vlm_config", lambda: cfg)

        calls: list[tuple[Any, ...]] = []

        def fake_ensure(*args: Any, **_kw: Any) -> bool:
            calls.append(args)
            return True

        from cc_vlm import server_manager

        monkeypatch.setattr(server_manager, "ensure_running", fake_ensure)

        preload_hook.run_preload_sync()

        assert calls == []


class TestShutdownHook:
    """`shutdown_hook.main()` always invokes server_manager.shutdown(only_if_ours=True)."""

    def test_calls_shutdown_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cc_vlm import server_manager

        calls: list[dict[str, Any]] = []

        def fake_shutdown(**kw: Any) -> None:
            calls.append(kw)

        monkeypatch.setattr(server_manager, "shutdown", fake_shutdown)

        shutdown_hook.main()

        assert calls == [{"only_if_ours": True}]

    def test_shutdown_swallows_exceptions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SessionEnd hook must not raise — that would log noise into CC's shutdown path."""
        from cc_vlm import server_manager

        def raise_(**_kw: Any) -> None:
            raise RuntimeError("shouldnt-bubble")

        monkeypatch.setattr(server_manager, "shutdown", raise_)

        shutdown_hook.main()  # must not raise
