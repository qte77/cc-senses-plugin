"""TTS engine abstraction and implementations."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol


class TTSEngine(Protocol):
    """Protocol for text-to-speech engines."""

    def synthesize(
        self, text: str, output_path: str, *, voice: str | None = None, speed: float = 1.0
    ) -> None: ...

    def available(self) -> bool: ...

    @property
    def name(self) -> str: ...


_ESPEAK_DEFAULT_VOICE = "en-us"


class EspeakEngine:
    """espeak-ng engine — lightweight, zero-config fallback."""

    @property
    def name(self) -> str:
        return "espeak-ng"

    def available(self) -> bool:
        return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None

    def _cmd(self) -> str:
        if shutil.which("espeak-ng") is not None:
            return "espeak-ng"
        return "espeak"

    def synthesize(
        self, text: str, output_path: str, *, voice: str | None = None, speed: float = 1.0
    ) -> None:
        # Ignore Piper voice names (contain underscores like en_US-amy-medium)
        if voice is not None and "_" in voice:
            voice = _ESPEAK_DEFAULT_VOICE
        cmd = [self._cmd(), "-w", output_path, "-v", voice or _ESPEAK_DEFAULT_VOICE]
        wpm = int(175 * speed)
        cmd.extend(["-s", str(wpm)])
        cmd.append(text)
        subprocess.run(cmd, check=True, capture_output=True)


_PIPER_MODEL_DIRS = [
    Path.home() / ".local" / "share" / "piper-models",
    Path(tempfile.gettempdir()) / "piper-models",
]

_PIPER_VOICE_RE = re.compile(r"[A-Za-z]{2,3}_[A-Za-z]{2}-[A-Za-z0-9_]+-(?:x_low|low|medium|high)")
_PIPER_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


class PiperEngine:
    """Piper TTS engine — neural VITS, good quality, fast."""

    @property
    def name(self) -> str:
        return "piper"

    def available(self) -> bool:
        return shutil.which("piper") is not None

    @staticmethod
    def _resolve_model(voice: str) -> str:
        """Resolve voice name to .onnx model path, downloading if needed."""
        if voice.endswith(".onnx") and Path(voice).exists():
            return voice

        # Plain published voice names only: no separators or `..` may reach the model path or URL.
        if not _PIPER_VOICE_RE.fullmatch(voice):
            msg = f"Cannot resolve Piper voice: {voice}. Provide full .onnx path."
            raise RuntimeError(msg)

        onnx_name = f"{voice}.onnx"
        for model_dir in _PIPER_MODEL_DIRS:
            candidate = model_dir / onnx_name
            if candidate.exists():
                return str(candidate)

        # Auto-download to first writable dir
        # Voice path: en/en_US/amy/medium/en_US-amy-medium.onnx
        parts = voice.split("-")
        if len(parts) >= 3:
            lang = parts[0]  # en_US
            lang_short = lang.split("_")[0]  # en
            speaker = parts[1]  # amy
            quality = parts[2]  # medium
            url = f"{_PIPER_HF_BASE}/{lang_short}/{lang}/{speaker}/{quality}/{onnx_name}"
            json_url = f"{url}.json"
        else:
            msg = f"Cannot resolve Piper voice: {voice}. Provide full .onnx path."
            raise RuntimeError(msg)

        import urllib.request

        dest_dir = _PIPER_MODEL_DIRS[0]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / onnx_name
        dest_json = dest_dir / f"{onnx_name}.json"
        urllib.request.urlretrieve(url, dest)  # noqa: S310 -- fixed https base URL
        urllib.request.urlretrieve(json_url, dest_json)  # noqa: S310 -- fixed https base URL
        return str(dest)

    def synthesize(
        self, text: str, output_path: str, *, voice: str | None = None, speed: float = 1.0
    ) -> None:
        voice = voice or "en_US-amy-medium"
        model_path = self._resolve_model(voice)
        cmd = [
            "piper",
            "--model",
            model_path,
            "--output_file",
            output_path,
            "--length_scale",
            str(1.0 / speed),
        ]
        subprocess.run(cmd, input=text.encode(), check=True, capture_output=True)


_KOKORO_MODEL_DIR = Path.home() / ".local" / "share" / "kokoro-models"
_KOKORO_RELEASE_BASE = "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0"
_KOKORO_MODEL_FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]


class KokoroEngine:
    """Kokoro TTS engine — best local quality, 82M params."""

    @property
    def name(self) -> str:
        return "kokoro"

    def available(self) -> bool:
        return shutil.which("kokoro-tts") is not None

    @staticmethod
    def _ensure_models(model_dir: Path) -> Path:
        """Ensure model files exist, downloading if needed. Returns model dir."""
        model_dir.mkdir(parents=True, exist_ok=True)
        for fname in _KOKORO_MODEL_FILES:
            dest = model_dir / fname
            if not dest.exists():
                import urllib.request

                url = f"{_KOKORO_RELEASE_BASE}/{fname}"
                urllib.request.urlretrieve(url, dest)  # noqa: S310 -- fixed https base URL
        return model_dir

    def synthesize(
        self, text: str, output_path: str, *, voice: str | None = None, speed: float = 1.0
    ) -> None:
        import os
        import tempfile

        # Ignore Piper/espeak voice names — Kokoro uses its own format (e.g., af_sarah)
        if voice is not None and "-" in voice:
            voice = "af_sarah"
        voice = voice or "af_sarah"
        model_dir = self._ensure_models(_KOKORO_MODEL_DIR)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(text)
            txt_path = f.name
        cmd = [
            "kokoro-tts",
            txt_path,
            output_path,
            "--voice",
            voice,
            "--lang",
            "en-us",
            "--speed",
            str(speed),
            "--model",
            str(model_dir / "kokoro-v1.0.onnx"),
            "--voices",
            str(model_dir / "voices-v1.0.bin"),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        finally:
            os.unlink(txt_path)


class EdgeTTSEngine:
    """Edge TTS engine — Microsoft cloud TTS, fast (~1s), high quality."""

    _DEFAULT_VOICE = "en-US-AriaNeural"

    @property
    def name(self) -> str:
        return "edge-tts"

    def available(self) -> bool:
        try:
            __import__("edge_tts")
            return True
        except ImportError:
            return False

    def synthesize(
        self, text: str, output_path: str, *, voice: str | None = None, speed: float = 1.0
    ) -> None:
        import asyncio

        import edge_tts

        # Edge TTS uses rate as percentage string: "+0%", "+50%", "-25%"
        rate_pct = int((speed - 1.0) * 100)
        rate_str = f"{rate_pct:+d}%"

        tts_voice = voice if voice and "Neural" in voice else self._DEFAULT_VOICE
        communicate = edge_tts.Communicate(text, tts_voice, rate=rate_str)

        # edge-tts saves as mp3 — player.py handles mp3 via mpv/ffplay
        asyncio.run(communicate.save(output_path))


_ENGINE_TYPES = [KokoroEngine, EdgeTTSEngine, PiperEngine, EspeakEngine]


def resolve_engine(engine_name: str = "auto") -> TTSEngine:
    """Resolve a TTS engine by name or auto-detect best available."""
    name_map: dict[str, type] = {
        "espeak": EspeakEngine,
        "espeak-ng": EspeakEngine,
        "piper": PiperEngine,
        "kokoro": KokoroEngine,
        "edge": EdgeTTSEngine,
        "edge-tts": EdgeTTSEngine,
    }
    if engine_name != "auto":
        cls = name_map.get(engine_name)
        if cls is None:
            msg = f"Unknown engine: {engine_name}. Available: {', '.join(name_map)}"
            raise ValueError(msg)
        engine = cls()
        if not engine.available():
            msg = f"Engine '{engine_name}' is not installed"
            raise RuntimeError(msg)
        return engine

    for cls in _ENGINE_TYPES:
        engine = cls()
        if engine.available():
            return engine

    msg = "No TTS engine found. Install kokoro-tts, piper, or espeak-ng."
    raise RuntimeError(msg)
