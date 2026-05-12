---
name: listen
description: Transcribe speech using local STT. Use when the user wants voice input or offline audio transcription.
compatibility: Designed for Claude Code
metadata:
  allowed-tools: Bash, Read
  argument-hint: [audio-file.wav] or --toggle
  stability: development
---

Transcribe speech using local speech-to-text.

## Usage

- `/listen` — start/stop listening via microphone
- `/listen recording.wav` — transcribe an audio file
- `/listen --toggle` — enable/disable auto-listen mode

## Implementation

```bash
python -m cc_stt $ARGUMENTS
```

## Configuration

See [`.cc-senses.example.toml`](../../.cc-senses.example.toml) `[stt]` section for the full schema and `CC_STT_*` env overrides.

## Status

Prototype — config, engine protocol, mic capture, utterance buffer, PTY injection, and live listen pipeline are implemented.
