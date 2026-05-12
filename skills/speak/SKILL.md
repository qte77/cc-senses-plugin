---
name: speak
description: Speak text aloud using local TTS. Use when the user wants Claude's output read aloud or to toggle auto-read mode.
compatibility: Designed for Claude Code
metadata:
  allowed-tools: Bash, Read
  argument-hint: [text to speak or --toggle]
  stability: development
---

Speak text aloud using local text-to-speech.

## Usage

- `/speak Hello world` — speak specific text
- `/speak --toggle` — enable/disable auto-read mode
- `/speak --voice en_GB-alan` — use a specific voice

## Implementation

```bash
uv run python -m cc_tts.speak $ARGUMENTS
```

## Configuration

See [`.cc-senses.example.toml`](../../.cc-senses.example.toml) `[tts]` section for the full schema and `CC_TTS_*` env overrides.

## Delivery modes

Three paths from text to audio (Stop hook, stream-json pipe, PTY proxy). See [`docs/architecture.md`](../../docs/architecture.md#tts-delivery-modes) for the comparison table and [`docs/adr/0001-tts-delivery-modes.md`](../../docs/adr/0001-tts-delivery-modes.md) for the rationale.

Do not combine Stop hook + PTY proxy — causes double speaking.

## Voice Loop (STT + TTS)

For the full bidirectional flow (`/speak --toggle` → `/voice` → speak → response spoken back), see [`docs/UserStory.md`](../../docs/UserStory.md#flow-a-voice-loop) Flow A.
