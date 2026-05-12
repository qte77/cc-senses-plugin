# Architecture

Single source of truth for cc-senses-bridge pipeline and engine details.
ADRs in `docs/adr/` record decisions; this file records the current design.

---

## Overview

cc-senses-bridge adds three subsystems to Claude Code:

| Subsystem | Command | Role |
|---|---|---|
| TTS | `/speak`, `cc-tts-stream`, `cc-tts-repl` | Speak Claude's output |
| STT | `/listen` | Transcribe voice input |
| VLM | `/see` | Describe screen content as text |

All three use a **Protocol-based engine abstraction**: a `Protocol` class
defines the interface (`synthesize` / `transcribe` / `describe`), concrete
engine classes implement it, and a `resolve_*` function auto-detects the best
available engine at runtime. Adding a new engine is a single-file change.

---

## TTS Pipeline

**Flow**: text → sentence buffer → engine → WAV/MP3 → player

Engine priority (auto-detect order): `kokoro > edge-tts > piper > espeak`

### TTS delivery modes

| Mode | Entry point | Interactive | First audio | Notes |
|---|---|---|---|---|
| **Stop hook** (default) | `/speak --toggle` | Yes | ~1-2 s after response ends | Full Ink UI; sentence-by-sentence via `SentenceBuffer` |
| **Stream-json pipe** | `cc-tts-stream "prompt"` | No (single prompt) | ~0.5-1 s | True mid-generation streaming; no Ink UI |
| **REPL** | `cc-tts-repl` | Yes | ~0.5-1 s | Interactive bidirectional stream-json; no Ink UI |
| PTY proxy (parked) | `cc-tts-wrap claude` | Yes | ~0.5 s | Brittle — scrapes Ink output; do not promote |

Do not combine Stop hook + PTY proxy — causes double-speaking.

See `docs/adr/0001-tts-delivery-modes.md` for rationale.

### TTS engine comparison

| Engine | Quality | Latency | Requires | Notes |
|---|---|---|---|---|
| **kokoro** | Best | ~1 s | `kokoro-tts` binary + ONNX models | 82M params; auto-downloads models |
| **edge-tts** | High | ~1 s | `edge_tts` Python package + internet | Microsoft cloud; mp3 output |
| **piper** | Good | ~0.5 s | `piper` binary + ONNX voice models | Neural VITS; auto-downloads voices |
| **espeak** | Basic | <0.1 s | `espeak-ng` or `espeak` binary | Zero-config fallback; always available |

---

## STT Pipeline

**Flow**: mic capture → VAD buffer → utterance boundary → engine → text → inject

Engine priority (auto-detect order): `moonshine > vosk`

### STT engine comparison

| Engine | Model size | Latency | Language | Notes |
|---|---|---|---|---|
| **moonshine** | 27 M params | ~400 ms | English | ONNX runtime; best for code/commands |
| **vosk** | ~50 MB | ~500 ms | 20+ languages | Broader language support; smaller models |
| Whisper (deferred) | varies | >1 s | Many | Domain fine-tunes; heavier runtime (#31) |
| Parakeet-TDT (deferred) | — | — | Multilingual | CC-BY-4.0; via onnx-asr (#32) |

VAD buffering prevents partial utterance submission.
See `docs/adr/0002-stt-engine-selection.md` for rationale.

---

## VLM Pipeline

**Flow**: screen capture → resize (longest edge ≤ 768 px) → BLAKE3 hash →
cache check → VLM → text description → inject into prompt

Engine priority (auto-detect order): `llamacpp` → `llamaserver` (in-process preferred when configured; HTTP fallback when only `server_url` is set)

### VLM engine comparison

| Engine | Backend | Daemon | RAM idle | Latency (warm) | Notes |
|---|---|---|---|---|---|
| **llamacpp** (default) | llama-cpp-python | None | 0 (but cold-starts every `/see` — fresh Python process) | ~200-500 ms (within one process; rare for CLI) | In-process; no HTTP. Cold-starts on every `/see` invocation. |
| **llamaserver** | `llama-server` HTTP | Yes (user-managed in Phase 1; lazy auto-spawn in Phase 2; preloaded in Phase 3) | ~1-2 GB while alive | ~200-500 ms (genuinely warm across `/see` calls) | Same llama.cpp binary as in-process; unlocks SmolVLM2, Qwen3-VL, and any GGUF llama.cpp supports without waiting for `abetlen/llama-cpp-python` handler PRs |
| ClaudeVisionEngine (deferred) | Claude Vision API | None | 0 | ~1-3 s | ~1,600 tokens/call; opt-in `--vision` |

**Why `llama-server` and not Ollama**: same llama.cpp binary already used by the in-process path, no extra daemon family to support, no Ollama-as-dependency. Ollama was considered and rejected on those grounds during the #91 research pass.

BLAKE3 frame cache: unchanged screen + same template = 0 VLM calls.
Cold start: 3-5 s (model load). Warm page cache: 1-2 s. In-process reuse: 200-500 ms.

### Supported VLM models (llama-cpp-python handlers)

| handler_name | llama_cpp class | Model family |
|---|---|---|
| `moondream` (default) | `MoondreamChatHandler` | Moondream2 (~0.9 GB Q4, fastest CPU path) |
| `qwen2.5vl` | `Qwen25VLChatHandler` | Qwen2.5-VL-2B/3B/7B (richer output, ~1.6 GB Q4) |
| `llava15` | `Llava15ChatHandler` | LLaVA 1.5 |
| `llava16` | `Llava16ChatHandler` | LLaVA 1.6 |
| `minicpmv` | `MiniCPMv26ChatHandler` | MiniCPM-V 2.6 |
| `nanollava` | `NanollavaChatHandler` | NanoLLaVA |

Default chosen for smallest CPU footprint; install via `make setup_see`.
For richer output swap to `qwen2.5vl` via `make setup_see_qwen25`.

### VLM token budget

| Path | Tokens/call | Notes |
|---|---|---|
| `/see` (local VLM → text) | ~120 | Default |
| `/see` cache hit | 0 | Same frame hash + template |
| Claude Vision API (deferred) | ~1,600 | Opt-in `--vision` flag |

See `docs/adr/0003-vlm-screen-sharing.md` for rationale.

---

## Prompt templates (VLM)

Templates cap VLM output at source to keep injected context small:

| Template | Focus |
|---|---|
| `generic` | Free-form ≤100-word description |
| `terminal` | Last command, exit status, errors (max 80 words) |
| `editor` | Filename, cursor line, diagnostics |
| `browser` | Page title, main heading, banners |
| `gui` | Active window, focused element, dialog text |
