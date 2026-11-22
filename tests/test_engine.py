"""Tests for cc_tts.engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cc_tts.engine import EspeakEngine, KokoroEngine, PiperEngine, resolve_engine


class TestEspeakEngine:
    def test_name(self) -> None:
        assert EspeakEngine().name == "espeak-ng"

    @patch("shutil.which", return_value="/usr/bin/espeak-ng")
    def test_available_when_installed(self, mock_which: object) -> None:
        assert EspeakEngine().available() is True

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_missing(self, mock_which: object) -> None:
        assert EspeakEngine().available() is False

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/espeak-ng")
    def test_synthesize_calls_espeak(
        self, mock_which: object, mock_run: object, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.wav")
        engine = EspeakEngine()
        engine.synthesize("hello", out, voice="en", speed=1.0)
        mock_run.assert_called_once()  # type: ignore[union-attr]
        cmd = mock_run.call_args[0][0]  # type: ignore[union-attr]
        assert cmd[0] == "espeak-ng"
        assert "-w" in cmd
        assert "hello" in cmd

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/espeak-ng")
    def test_synthesize_ignores_piper_voice(
        self, mock_which: object, mock_run: object, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.wav")
        engine = EspeakEngine()
        engine.synthesize("hello", out, voice="en_US-amy-medium")
        cmd = mock_run.call_args[0][0]  # type: ignore[union-attr]
        assert "en_US-amy-medium" not in cmd
        assert "en-us" in cmd


class TestPiperEngine:
    def test_name(self) -> None:
        assert PiperEngine().name == "piper"

    @patch("shutil.which", return_value="/usr/bin/piper")
    def test_available_when_installed(self, mock_which: object) -> None:
        assert PiperEngine().available() is True

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/piper")
    def test_synthesize_pipes_text(
        self, mock_which: object, mock_run: object, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.wav")
        engine = PiperEngine()
        engine.synthesize("hello", out)
        mock_run.assert_called_once()  # type: ignore[union-attr]
        assert mock_run.call_args.kwargs.get("input") == b"hello"  # type: ignore[union-attr]

    @pytest.mark.parametrize(
        "voice",
        ["/tmp/x-a-b", "../../../../tmp/x-a-b", "en_US/../x-amy-medium", "en_US-amy\\medium", "en_US-amy-medium\n"],
    )
    def test_resolve_model_rejects_path_like_voice(self, voice: str, tmp_path: Path) -> None:
        with (
            patch("cc_tts.engine._PIPER_MODEL_DIRS", [tmp_path / "models"]),
            patch("urllib.request.urlretrieve") as mock_get,
            pytest.raises(RuntimeError, match="Cannot resolve Piper voice"),
        ):
            PiperEngine._resolve_model(voice)
        mock_get.assert_not_called()
        assert not (tmp_path / "models").exists()

    def test_resolve_model_downloads_plain_voice_into_model_dir(self, tmp_path: Path) -> None:
        models = tmp_path / "models"
        with (
            patch("cc_tts.engine._PIPER_MODEL_DIRS", [models]),
            patch("urllib.request.urlretrieve") as mock_get,
        ):
            result = PiperEngine._resolve_model("en_GB-northern_english_male-medium")
        assert result == str(models / "en_GB-northern_english_male-medium.onnx")
        assert mock_get.call_count == 2


class TestKokoroEngine:
    def test_name(self) -> None:
        assert KokoroEngine().name == "kokoro"

    @patch("shutil.which", return_value="/usr/bin/kokoro-tts")
    def test_available_when_installed(self, mock_which: object) -> None:
        assert KokoroEngine().available() is True

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_missing(self, mock_which: object) -> None:
        assert KokoroEngine().available() is False

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/kokoro-tts")
    def test_synthesize_writes_to_file(
        self, mock_which: object, mock_run: object, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.wav")
        engine = KokoroEngine()
        engine.synthesize("hello", out, voice="af_sarah")
        mock_run.assert_called_once()  # type: ignore[union-attr]
        cmd = mock_run.call_args[0][0]  # type: ignore[union-attr]
        assert cmd[0] == "kokoro-tts"
        assert out in cmd

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/kokoro-tts")
    def test_synthesize_ignores_piper_voice(
        self, mock_which: object, mock_run: object, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.wav")
        engine = KokoroEngine()
        engine.synthesize("hello", out, voice="en_US-amy-medium")
        cmd = mock_run.call_args[0][0]  # type: ignore[union-attr]
        assert "en_US-amy-medium" not in cmd
        assert "af_sarah" in cmd


class TestResolveEngine:
    @patch("cc_tts.engine.EdgeTTSEngine.available", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_raises_when_no_engine(self, mock_which: object, mock_edge: object) -> None:
        with pytest.raises(RuntimeError, match="No TTS engine found"):
            resolve_engine("auto")

    @patch("shutil.which", return_value=None)
    def test_raises_for_unknown_engine(self, mock_which: object) -> None:
        with pytest.raises(ValueError, match="Unknown engine"):
            resolve_engine("nonexistent")

    @patch(
        "shutil.which",
        side_effect=lambda x: "/usr/bin/kokoro-tts" if x == "kokoro-tts" else None,
    )
    def test_auto_prefers_kokoro(self, mock_which: object) -> None:
        engine = resolve_engine("auto")
        assert engine.name == "kokoro"

    @patch("cc_tts.engine.EdgeTTSEngine.available", return_value=False)
    @patch("shutil.which", side_effect=lambda x: "/usr/bin/espeak-ng" if x == "espeak-ng" else None)
    def test_auto_falls_back_to_espeak(self, mock_which: object, mock_edge: object) -> None:
        engine = resolve_engine("auto")
        assert engine.name == "espeak-ng"

    @patch("shutil.which", return_value=None)
    def test_explicit_unavailable_raises(self, mock_which: object) -> None:
        with pytest.raises(RuntimeError, match="not installed"):
            resolve_engine("espeak")
