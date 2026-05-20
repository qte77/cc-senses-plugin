"""Tests for cc_stt.pty_input."""

from __future__ import annotations

import os
import pty
import select

from cc_stt.pty_input import inject_text


def _read_available(fd: int, timeout: float = 1.0) -> bytes:
    """Read available data from fd with timeout. Returns empty bytes on timeout."""
    r, _, _ = select.select([fd], [], [], timeout)
    if fd in r:
        return os.read(fd, 4096)
    return b""


class TestInjectText:
    def test_injects_text_to_pty(self) -> None:
        """Text written to master_fd echoes back (canonical mode echo)."""
        master_fd, slave_fd = pty.openpty()
        try:
            inject_text(master_fd, "hello world", newline=True)
            # In canonical mode, PTY echoes input back to master
            data = _read_available(master_fd)
            assert b"hello world" in data
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_empty_text_is_noop(self) -> None:
        master_fd, slave_fd = pty.openpty()
        try:
            inject_text(master_fd, "")
            inject_text(master_fd, "   ")
            data = _read_available(master_fd, timeout=0.1)
            assert data == b""
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_writes_raw_bytes(self) -> None:
        """Verify os.write is called with encoded text."""
        master_fd, slave_fd = pty.openpty()
        try:
            inject_text(master_fd, "abc")
            # Without newline, canonical mode buffers on slave side
            # but the write still happens — verify via echo on master
            inject_text(master_fd, "\n", newline=False)
            # Force the line through by injecting actual newline char
            data = _read_available(master_fd)
            assert b"abc" in data
        finally:
            os.close(master_fd)
            os.close(slave_fd)
