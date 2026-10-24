"""Hook handler for auto-listen mode."""

from __future__ import annotations

from cc_stt.config import load_stt_config


def should_auto_listen() -> bool:
    """Check if auto_listen is enabled in STT config.

    Returns False on any config error to avoid blocking Claude Code.
    """
    try:
        config = load_stt_config()
        return config.auto_listen
    except (Exception, SystemExit):
        return False
