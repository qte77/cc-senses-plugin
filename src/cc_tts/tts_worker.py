"""Shared TTS queue worker — pulls sentences and speaks them."""

from __future__ import annotations

import queue
import sys
from collections.abc import Callable

from cc_tts.speak import synthesize_and_play


def tts_worker(
    q: queue.Queue[str | None],
    *,
    on_speak: Callable[[str], None] | None = None,
) -> None:
    """Pull sentences from queue and speak them. Stops on None sentinel.

    Batches multiple queued sentences into one synthesis call to reduce
    engine cold-start overhead (e.g. Kokoro ONNX model load).
    """
    speak = on_speak or synthesize_and_play
    while True:
        sentence = q.get()
        if sentence is None:
            break

        # Drain any additional sentences already queued — batch into one call.
        batch = [sentence]
        while True:
            try:
                extra = q.get_nowait()
            except queue.Empty:
                break
            if extra is None:
                # Sentinel found — speak batch then exit.
                _speak_batch(speak, batch)
                return
            batch.append(extra)

        _speak_batch(speak, batch)


def _speak_batch(speak: Callable[[str], None], batch: list[str]) -> None:
    """Speak a batch of sentences as one combined text."""
    text = " ".join(batch)
    try:
        speak(text)
    except Exception as exc:
        print(f"[cc-senses-bridge] TTS error: {exc}", file=sys.stderr)
