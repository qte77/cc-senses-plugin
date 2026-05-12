"""ANSI stripping and content classification for PTY output."""

from __future__ import annotations

import re

from cc_tts.sentence_buffer import SentenceBuffer

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\].*?\x07")
_PRINTABLE_ASCII = re.compile(r"[^\x20-\x7e]")


def _is_nonalpha_line(line: str) -> bool:
    """Return True if line is >80% non-alphabetic characters."""
    if len(line) < 4:
        return False
    alpha = sum(1 for c in line if c.isalpha())
    return alpha / len(line) < 0.2


class StreamFilter:
    """Filters PTY output for TTS: strips ANSI, skips code/tool/spinner content."""

    def __init__(self, buffer: SentenceBuffer) -> None:
        self.buffer = buffer
        self._in_code_block = False
        self._byte_remainder = b""

    def feed(self, raw: bytes) -> bytes:
        """Process raw PTY bytes. Returns original bytes for terminal passthrough.

        Side effect: feeds cleaned text to the SentenceBuffer.
        """
        data = self._byte_remainder + raw
        self._byte_remainder = b""

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            # Partial UTF-8 at boundary — stash trailing bytes
            for i in range(1, 4):
                try:
                    text = data[:-i].decode("utf-8")
                    self._byte_remainder = data[-i:]
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = data.decode("utf-8", errors="replace")

        clean = _ANSI_ESCAPE.sub("", text)

        # Normalize PTY line endings, then emulate terminal \r semantics:
        # \r means "overwrite from start of line" — keep only text after last \r.
        clean = clean.replace("\r\n", "\n")
        clean = re.sub(r"[^\n]*\r", "", clean)

        for line in clean.split("\n"):
            # Code block toggle
            stripped = line.strip()
            if stripped.startswith("```"):
                self._in_code_block = not self._in_code_block
                continue

            if self._in_code_block:
                continue

            # Keep only printable ASCII (drops box-drawing, emoji, etc.)
            stripped = _PRINTABLE_ASCII.sub("", stripped).strip()

            # High non-alpha lines (diffs, separators)
            if _is_nonalpha_line(stripped):
                continue

            # Feed clean text to sentence buffer
            if stripped:
                self.buffer.feed(stripped + " ")

        return raw

    def finish(self) -> None:
        """Flush remaining content to the buffer."""
        self.buffer.flush()
