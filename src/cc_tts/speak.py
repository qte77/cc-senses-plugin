"""Main entry point: text → speech synthesis and playback."""

from __future__ import annotations

import atexit
import os
import signal
import sys
import tempfile
from pathlib import Path

from cc_tts.config import TTSConfig, load_config
from cc_tts.engine import resolve_engine
from cc_tts.player import NoAudioDeviceError, play_audio
from cc_tts.preprocess import preprocess

_output_counter = 0

# PID file for --stop interrupt. Stores the current speak PGID (process group).
_PID_FILE = Path.home() / ".cache" / "cc-senses-bridge" / "speak.pid"


def _write_pidfile() -> None:
    """Write current process group ID to pidfile for --stop to find."""
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    pgid = os.getpgrp()
    _PID_FILE.write_text(str(pgid))
    atexit.register(_clear_pidfile)


def _clear_pidfile() -> None:
    """Remove pidfile on clean exit."""
    try:
        _PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _stop_playback() -> int:
    """Read pidfile, kill process group, clear pidfile. Returns exit code."""
    if not _PID_FILE.exists():
        print("No TTS playback running (no pidfile).", file=sys.stderr)
        return 1
    try:
        pgid = int(_PID_FILE.read_text().strip())
    except (OSError, ValueError) as exc:
        print(f"Invalid pidfile: {exc}", file=sys.stderr)
        _clear_pidfile()
        return 1
    try:
        os.killpg(pgid, signal.SIGTERM)
        print(f"Stopped TTS playback (pgid={pgid})")
    except ProcessLookupError:
        print("TTS playback already exited.", file=sys.stderr)
    finally:
        _clear_pidfile()
    return 0


def _next_output_path(output_dir: Path) -> str:
    """Return next sequential WAV path in the output directory."""
    global _output_counter  # noqa: PLW0603
    _output_counter += 1
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / f"{_output_counter:03d}.wav")


def synthesize_and_play(text: str, config: TTSConfig | None = None) -> None:
    """Preprocess text, synthesize speech, and play audio.

    Set CC_TTS_OUTPUT_DIR to save WAVs to a directory instead of playing.
    """
    config = config or load_config()
    text = preprocess(text, max_chars=config.max_chars)

    if not text:
        return

    engine = resolve_engine(config.engine)
    output_dir = os.environ.get("CC_TTS_OUTPUT_DIR")

    if output_dir:
        wav_path = _next_output_path(Path(output_dir))
        engine.synthesize(text, wav_path, voice=config.voice, speed=config.speed)
        print(f"WAV saved: {wav_path}", file=sys.stderr)
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        engine.synthesize(text, f.name, voice=config.voice, speed=config.speed)
        try:
            play_audio(f.name, player=config.player, blocking=True)
        except NoAudioDeviceError:
            print(f"No audio device. WAV saved: {f.name}", file=sys.stderr)


def _toggle_auto_read() -> None:
    """Toggle auto_read in .cc-senses.toml [tts] section."""
    from cc_voice_common.config import find_config_file

    config_path = find_config_file()
    if config_path is None:
        print("No .cc-senses.toml found — create one first", file=sys.stderr)
        sys.exit(1)

    content = config_path.read_text()
    if "auto_read = true" in content:
        content = content.replace("auto_read = true", "auto_read = false", 1)
        print("auto_read: true → false")
    elif "auto_read = false" in content:
        content = content.replace("auto_read = false", "auto_read = true", 1)
        print("auto_read: false → true")
    else:
        print("auto_read field not found in .cc-senses.toml [tts] section", file=sys.stderr)
        sys.exit(1)
    config_path.write_text(content)


def main() -> None:
    """CLI entry point for cc-senses-bridge speak.

    Usage:
        python -m cc_tts.speak <text>       speak the given text
        python -m cc_tts.speak --toggle     flip auto_read in .cc-senses.toml
        python -m cc_tts.speak --help       show usage
    """
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m cc_tts.speak [--toggle | --stop | --stream | <text>]")
        print("  <text>    Speak the given text via the configured TTS engine")
        print("  --stream  Stream audio directly to player (no temp files)")
        print("  --stop    Interrupt ongoing TTS playback (SIGTERM to process group)")
        print("  --toggle  Flip auto_read in .cc-senses.toml (enables/disables Stop hook TTS)")
        print("  --help    Show this message")
        return

    if "--stop" in sys.argv:
        sys.exit(_stop_playback())

    if "--toggle" in sys.argv:
        _toggle_auto_read()
        return

    if len(sys.argv) < 2:
        print(
            "Usage: python -m cc_tts.speak [--toggle | --help | <text to speak>]", file=sys.stderr
        )
        sys.exit(1)

    stream = "--stream" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--stream"]
    text = " ".join(args)

    _write_pidfile()

    if stream:
        from cc_tts.edge_stream import speak_streaming

        config = load_config()
        speak_streaming(text, voice=config.voice, speed=config.speed, engine=config.engine)
    else:
        synthesize_and_play(text)


if __name__ == "__main__":
    main()
