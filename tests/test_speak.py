"""Tests for cc_tts.speak — TDD RED phase."""

from __future__ import annotations

import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cc_tts.speak import synthesize_and_play


class TestSynthesizeAndPlay:
    @patch("cc_tts.speak.play_audio")
    @patch("cc_tts.speak.resolve_engine")
    @patch("cc_tts.speak.preprocess", side_effect=lambda t, **kw: t)
    @patch("cc_tts.speak.load_config")
    def test_calls_engine_and_player(
        self,
        mock_config: MagicMock,
        mock_preprocess: MagicMock,
        mock_resolve: MagicMock,
        mock_play: MagicMock,
    ) -> None:
        from cc_tts.config import TTSConfig

        mock_config.return_value = TTSConfig()
        mock_engine = MagicMock()
        mock_resolve.return_value = mock_engine

        synthesize_and_play("Hello world")

        mock_engine.synthesize.assert_called_once()
        mock_play.assert_called_once()

    @patch("cc_tts.speak.play_audio")
    @patch("cc_tts.speak.resolve_engine")
    @patch("cc_tts.speak.preprocess", side_effect=lambda t, **kw: t)
    @patch("cc_tts.speak.load_config")
    def test_passes_voice_and_speed(
        self,
        mock_config: MagicMock,
        mock_preprocess: MagicMock,
        mock_resolve: MagicMock,
        mock_play: MagicMock,
    ) -> None:
        from cc_tts.config import TTSConfig

        mock_config.return_value = TTSConfig(voice="en_GB-alan", speed=1.5)
        mock_engine = MagicMock()
        mock_resolve.return_value = mock_engine

        synthesize_and_play("test")

        call_kwargs = mock_engine.synthesize.call_args
        assert call_kwargs.kwargs["voice"] == "en_GB-alan"
        assert call_kwargs.kwargs["speed"] == 1.5

    @patch("cc_tts.speak.play_audio")
    @patch("cc_tts.speak.resolve_engine")
    @patch("cc_tts.speak.preprocess", return_value="cleaned")
    @patch("cc_tts.speak.load_config")
    def test_preprocesses_text(
        self,
        mock_config: MagicMock,
        mock_preprocess: MagicMock,
        mock_resolve: MagicMock,
        mock_play: MagicMock,
    ) -> None:
        from cc_tts.config import TTSConfig

        mock_config.return_value = TTSConfig()
        mock_engine = MagicMock()
        mock_resolve.return_value = mock_engine

        synthesize_and_play("raw **markdown** text")

        mock_preprocess.assert_called_once()
        assert mock_engine.synthesize.call_args[0][0] == "cleaned"


class TestStopFlag:
    """--stop reads pidfile, sends SIGTERM to the recorded process group, clears pidfile."""

    def test_returns_1_when_pidfile_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("cc_tts.speak._PID_FILE", tmp_path / "missing.pid")
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stop"])

        from cc_tts.speak import main

        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_sends_sigterm_to_recorded_pgid_then_clears_pidfile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pidfile = tmp_path / "speak.pid"
        pidfile.write_text("12345")
        monkeypatch.setattr("cc_tts.speak._PID_FILE", pidfile)
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stop"])

        from cc_tts.speak import main

        with patch("cc_tts.speak.os.killpg") as mock_kill:
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)
        assert not pidfile.exists()

    def test_handles_already_exited_process_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pidfile = tmp_path / "speak.pid"
        pidfile.write_text("99999")
        monkeypatch.setattr("cc_tts.speak._PID_FILE", pidfile)
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stop"])

        from cc_tts.speak import main

        with patch("cc_tts.speak.os.killpg", side_effect=ProcessLookupError):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        assert not pidfile.exists()

    def test_returns_1_and_clears_invalid_pidfile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pidfile = tmp_path / "speak.pid"
        pidfile.write_text("not-a-pgid")
        monkeypatch.setattr("cc_tts.speak._PID_FILE", pidfile)
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stop"])

        from cc_tts.speak import main

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code == 1
        assert not pidfile.exists()


class TestStreamFlag:
    """--stream routes through edge_stream.speak_streaming and writes the pidfile."""

    @patch("cc_tts.edge_stream.speak_streaming")
    @patch("cc_tts.speak._write_pidfile")
    @patch("cc_tts.speak.load_config")
    def test_routes_to_speak_streaming_with_text(
        self,
        mock_config: MagicMock,
        mock_pidfile: MagicMock,
        mock_speak_streaming: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from cc_tts.config import TTSConfig

        mock_config.return_value = TTSConfig()
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stream", "Hello world"])

        from cc_tts.speak import main

        main()

        mock_speak_streaming.assert_called_once()
        # Stream flag must be stripped from the joined text argument.
        assert mock_speak_streaming.call_args[0][0] == "Hello world"

    @patch("cc_tts.edge_stream.speak_streaming")
    @patch("cc_tts.speak._write_pidfile")
    @patch("cc_tts.speak.load_config")
    def test_writes_pidfile_so_stop_can_interrupt(
        self,
        mock_config: MagicMock,
        mock_pidfile: MagicMock,
        mock_speak_streaming: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from cc_tts.config import TTSConfig

        mock_config.return_value = TTSConfig()
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stream", "test"])

        from cc_tts.speak import main

        main()

        mock_pidfile.assert_called_once()

    @patch("cc_tts.edge_stream.speak_streaming")
    @patch("cc_tts.speak._write_pidfile")
    @patch("cc_tts.speak.load_config")
    def test_passes_voice_speed_engine_from_config(
        self,
        mock_config: MagicMock,
        mock_pidfile: MagicMock,
        mock_speak_streaming: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from cc_tts.config import TTSConfig

        mock_config.return_value = TTSConfig(voice="af_sarah", speed=1.2, engine="edge")
        monkeypatch.setattr(sys, "argv", ["speak.py", "--stream", "x"])

        from cc_tts.speak import main

        main()

        kwargs = mock_speak_streaming.call_args.kwargs
        assert kwargs["voice"] == "af_sarah"
        assert kwargs["speed"] == 1.2
        assert kwargs["engine"] == "edge"
