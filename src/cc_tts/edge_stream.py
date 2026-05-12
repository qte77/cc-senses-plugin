"""Streaming TTS — pipe audio directly to player, no temp files."""

from __future__ import annotations

import shutil
import subprocess
import tempfile

from cc_tts.player import _detect_player  # pyright: ignore[reportPrivateUsage]


def speak_streaming(
    text: str, *, voice: str = "en-US-AriaNeural", speed: float = 1.0, engine: str = "auto"
) -> None:
    """Synthesize and play text, streaming audio to player where possible."""
    from cc_tts.preprocess import preprocess

    # Strip markdown, code blocks, URLs so TTS doesn't read "hash hash What we lose".
    text = preprocess(text)
    if not text:
        return

    if engine == "auto":
        # Priority: kokoro (best local) > piper > espeak > edge-tts (cloud, last resort)
        _fallbacks = [("kokoro-tts", "kokoro"), ("piper", "piper"), ("espeak-ng", "espeak")]
        for name, eng in _fallbacks:
            if shutil.which(name):
                engine = eng
                break
        else:
            try:
                __import__("edge_tts")
                engine = "edge"
            except ImportError:
                pass

    if engine in ("edge", "edge-tts"):
        _stream_edge(text, voice=voice, speed=speed)
    elif engine == "kokoro":
        _stream_kokoro(text, voice=voice, speed=speed)
    elif engine in ("espeak", "espeak-ng"):
        _stream_espeak(text, voice=voice, speed=speed)
    elif engine == "piper":
        _stream_piper(text, voice=voice, speed=speed)
    else:
        from cc_tts.config import load_config
        from cc_tts.speak import synthesize_and_play

        synthesize_and_play(text, config=load_config())


def _pipe_to_player(cmd: list[str], *, stdin_data: bytes | None = None) -> None:
    """Run engine cmd, pipe its stdout to the audio player.

    If stdin_data is provided, it's written to the engine's stdin (for piper).
    """
    _, player_cmd = _detect_player()

    engine = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_data else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    player = subprocess.Popen(
        [*player_cmd, "-"],
        stdin=engine.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if stdin_data and engine.stdin:
            engine.stdin.write(stdin_data)
            engine.stdin.close()
        engine.wait()
        player.wait()
    except KeyboardInterrupt:
        engine.terminate()
        player.terminate()


def _stream_espeak(text: str, *, voice: str, speed: float) -> None:
    """espeak-ng --stdout → player."""
    cmd_name = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
    espeak_voice = voice if voice and "_" not in voice else "en-us"
    wpm = str(int(175 * speed))
    _pipe_to_player([cmd_name, "--stdout", "-v", espeak_voice, "-s", wpm, text])


def _stream_piper(text: str, *, voice: str, speed: float) -> None:
    """echo text | piper --output-raw → player."""
    cmd = ["piper", "--output-raw"]
    if voice:
        cmd.extend(["--model", voice])
    if speed != 1.0:
        cmd.extend(["--length-scale", str(1.0 / speed)])
    _pipe_to_player(cmd, stdin_data=text.encode())


def _stream_kokoro(text: str, *, voice: str, speed: float) -> None:
    """kokoro-tts --stream plays directly to audio device (no pipe needed)."""
    from cc_tts.engine import _KOKORO_MODEL_DIR  # pyright: ignore[reportPrivateUsage]

    model_dir = _KOKORO_MODEL_DIR

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(text)
        f.flush()
        txt_path = f.name

    try:
        subprocess.run(
            [
                "kokoro-tts",
                txt_path,
                "--stream",
                "--voice",
                voice or "af_sarah",
                "--speed",
                str(speed),
                "--model",
                str(model_dir / "kokoro-v1.0.onnx"),
                "--voices",
                str(model_dir / "voices-v1.0.bin"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except KeyboardInterrupt:
        pass
    finally:
        import os

        os.unlink(txt_path)


def _stream_edge(text: str, *, voice: str, speed: float) -> None:
    """Edge TTS: async stream mp3 chunks directly to player."""
    import asyncio

    import edge_tts

    rate_pct = int((speed - 1.0) * 100)
    rate_str = f"{rate_pct:+d}%"
    tts_voice = voice if voice and "Neural" in voice else "en-US-AriaNeural"

    _, cmd = _detect_player()
    proc = subprocess.Popen(
        [*cmd, "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    async def _stream() -> None:
        assert proc.stdin is not None
        communicate = edge_tts.Communicate(text, tts_voice, rate=rate_str)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and "data" in chunk:
                proc.stdin.write(chunk["data"])  # pyright: ignore[reportTypedDictNotRequiredAccess]
        proc.stdin.close()

    try:
        asyncio.run(_stream())
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
