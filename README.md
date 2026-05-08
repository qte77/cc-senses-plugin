# cc-voice (prototype)

> **Status: Prototype** — end-to-end voice for Claude Code. TTS output via PTY proxy, STT input module scaffolded (config, engine, mic, VAD, PTY injection). Not production-ready.

[![License](https://img.shields.io/badge/license-Apache--2.0-58f4c2.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.7.0-58f4c2.svg)
[![CodeQL](https://github.com/qte77/cc-voice-plugin-prototype/actions/workflows/codeql.yaml/badge.svg)](https://github.com/qte77/cc-voice-plugin-prototype/actions/workflows/codeql.yaml)
[![CodeFactor](https://www.codefactor.io/repository/github/qte77/cc-voice-plugin-prototype/badge)](https://www.codefactor.io/repository/github/qte77/cc-voice-plugin-prototype)
[![Dependabot](https://github.com/qte77/cc-voice-plugin-prototype/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/qte77/cc-voice-plugin-prototype/actions/workflows/dependabot/dependabot-updates)
[![Lint MD and Links](https://github.com/qte77/cc-voice-plugin-prototype/actions/workflows/lint-md-links.yml/badge.svg)](https://github.com/qte77/cc-voice-plugin-prototype/actions/workflows/lint-md-links.yml)

End-to-end voice plugin for Claude Code. TTS speaks Claude's responses aloud, STT captures voice input via Moonshine/Vosk, VLM ingests the screen and feeds it as text into Claude's context for Claude to act on.

## Features

- **TTS** — `/speak` skill, Stop-hook auto-read, multi-engine (Kokoro / Piper / espeak-ng / edge-tts)
- **STT** — `/listen` skill, Moonshine/Vosk auto-detect, mic capture with VAD, PTY injection
- **VLM** — `/see` skill, in-process Moondream2 via llama-cpp-python (Qwen2.5-VL alt), screen → text into Claude's context (~120 tokens/call vs ~1,600 raw vision)

## Audio Examples

Session summary generated with three engines for comparison:

| Engine | Quality | File |
|--------|---------|------|
| espeak-ng | Robotic (rule-based) | [assets/audio/cc-tts-summary-espeak-ng.wav](assets/audio/cc-tts-summary-espeak-ng.wav) |
| Piper (amy) | Natural (neural VITS, ~60MB) | [assets/audio/cc-tts-summary-piper.wav](assets/audio/cc-tts-summary-piper.wav) |
| Kokoro (sarah) | Best local (82M params) | [assets/audio/cc-tts-summary-kokoro.wav](assets/audio/cc-tts-summary-kokoro.wav) |

## Quick Start

```bash
make setup_dev      # install package + dev deps
make setup_tts      # install espeak-ng + mpv (zero-config baseline)
make setup_piper    # install Piper (neural)
make setup_kokoro   # install Kokoro (best local)

cc-tts-wrap claude  # live PTY-wrapped TTS
cc-tts "Hello"      # one-shot CLI
```

## Configuration

Copy [`.cc-voice.example.toml`](.cc-voice.example.toml) to `.cc-voice.toml` and edit. All TTS, STT, and VLM fields plus `CC_*` env-var overrides are documented inline.

## CC Plugin

```bash
claude plugin install cc-voice@local
```

Provides `/speak`, `/listen`, `/see` skills and Stop-hook auto-read.

## Documentation

- [`.cc-voice.example.toml`](.cc-voice.example.toml) — config schema and env vars
- [Architecture](docs/architecture.md) — pipelines, engines, diagrams, token budgets
- [User flows](docs/UserStory.md) — personas and end-to-end use cases (incl. hotkey-stop playback)
- [ADRs](docs/adr/) — decision records (TTS modes, STT engines, VLM screen-sharing)
- [Roadmap](docs/roadmap/v0.5.x.md) — deferred ideas and rejected paths
- [Contributing](CONTRIBUTING.md) — setup, conventions, commit style

## Development

```bash
make validate       # lint + type check + test
make quick_validate # lint + type check only
VERBOSE=1 make test # full pytest output
```

## License

[Apache-2.0](LICENSE)
