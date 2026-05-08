# Engine & model landscape

What we evaluated for cc-voice's three subsystems — what shipped, what's
deferred, what's rejected and why. This is the **single source of truth
for engine/model decisions**; `docs/architecture.md` describes the
shipped engines in detail and `docs/roadmap/v0.5.x.md` tracks
time-bound work.

When a new engine or framework is researched, record the verdict here
so future sessions see "verified, here's why" and skip re-research.

## Hard constraints

Every candidate is judged against these. Anything that violates one is
a hard reject unless the violation is fixed upstream.

- **Local-first** — runs on the user's machine; no required cloud calls.
  Cloud engines (e.g. edge-tts) tolerated only as opt-in alternatives.
- **CPU-feasible** — works without a GPU; quantization (GGUF, ONNX
  INT8) preferred.
- **License: Apache 2.0 / MIT / BSD strongly preferred.** Anything with a
  revenue cap, BSL, or "research-only" clause is rejected unless it
  changes upstream.
- **Pluggable Protocol fit** — slots in as an additional engine class
  implementing the subsystem's `Protocol`; no daemon ownership of the
  process lifecycle, no full-framework adoption.
- **Half-duplex by design** — TTS and STT run sequentially; full-duplex
  frameworks are out of scope unless they contribute a single-component
  engine.

## TTS

### Shipped

See [`docs/architecture.md` § TTS engine comparison](architecture.md#tts-engine-comparison)
for full details (latency, deps, notes).

| handler | role | license |
|---|---|---|
| `kokoro` (auto-detect default) | best local quality | Apache 2.0 |
| `edge-tts` | high quality, requires internet | MIT (client); cloud service |
| `piper` | neural VITS, ~60 MB voice models | MIT |
| `espeak` | basic, zero-config fallback | GPL-3.0 (binary; cc-voice invokes via subprocess) |

### Tracked

- **#30** — `feat(tts): Kokoro voice blending via embedding math`. The
  only supported custom-voice path for Kokoro (StyleTTS2 → not
  fine-tunable). ~50 LOC + tests, shippable today.

### Considered / deferred

| Candidate | Status | Notes |
|---|---|---|
| **Orpheus-TTS via `llama-cpp-python`** | deferred | Enables Unsloth fine-tune path for domain-adapted TTS. Gate on actual user demand for fine-tuned custom voices (not pressing today). ~100 LOC + reuses the `llama-cpp-python` dep already pulled in by `cc_vlm`. |

### Rejected

| Candidate | Why not |
|---|---|
| **Unsloth → Kokoro fine-tune → GGUF** | Architecturally impossible: Kokoro is StyleTTS2 (not transformers-compatible), not in Unsloth's supported model list, and has no official fine-tune script. The correct custom-voice path is embedding blending — tracked as #30. |
| **k2-fsa/omnivoice** | Apache 2.0 header but model card adds "academic research purposes only" disclaimer; GPU/MPS-only inference path documented (no CPU/ONNX/GGUF). Existing TTS engines (kokoro/piper/espeak) all run CPU-only. Revisit if a clean Apache export with quantized CPU path ships. |

## STT

### Shipped

See [`docs/architecture.md` § STT engine comparison](architecture.md#stt-engine-comparison)
for full details.

| handler | role | license |
|---|---|---|
| `moonshine` (auto-detect default) | English, 27 M params, ONNX | MIT |
| `vosk` | 20+ languages, ~50 MB models | Apache 2.0 |

### Tracked

- **#31** — `feat(stt): Whisper engine via faster-whisper` — domain
  fine-tunes (medical, legal, accented speech) via PEFT/LoRA workflow.
  CC-BY-4.0 / MIT.
- **#32** — `feat(stt): Parakeet-TDT-0.6B-v3 engine via onnx-asr` —
  multilingual, CC-BY-4.0, CPU-friendly INT8 ONNX. Validated by NVIDIA
  NeMo as their default STT.

### Considered / deferred

(None currently.)

### Rejected

(None currently — no STT engines have been formally rejected.)

## VLM

### Shipped

See [`docs/architecture.md` § VLM engine comparison](architecture.md#vlm-engine-comparison)
and the supported-handlers table for full details.

| handler | role | license |
|---|---|---|
| `moondream` (default) | Moondream2, ~0.9 GB Q4, fastest CPU path | Apache 2.0 |
| `qwen2.5vl` | Qwen2.5-VL-2B/3B/7B, richer output, ~1.6 GB Q4 | Apache 2.0 |
| `llava15` / `llava16` | LLaVA 1.5 / 1.6 | Apache 2.0 |
| `minicpmv` | MiniCPM-V 2.6 | Apache 2.0 |
| `nanollava` | NanoLLaVA | Apache 2.0 |

All shipped via the single `LlamaCppVLMEngine` class in
`src/cc_vlm/engine.py`, dispatched on `handler_name`.

### Considered / deferred

To be filed as issues; placeholder list for now.

| Candidate | Status | Notes |
|---|---|---|
| **`LlamaServerVLMEngine` HTTP backend** | deferred (Phase 2) | Same `llama.cpp` binary as the in-process path — adds an HTTP-server engine class so users can run any GGUF llama.cpp supports without waiting for `abetlen/llama-cpp-python` handler PRs. Unlocks SmolVLM2-2.2B and Qwen3-VL-2B on the day llama.cpp supports them. Ollama considered and rejected (extra daemon family, Ollama-as-dependency). |
| **`Qwen3VLChatHandler` for in-process backend** | deferred (Phase 3) | Blocked on [`abetlen/llama-cpp-python` #2080](https://github.com/abetlen/llama-cpp-python/issues/2080). Add `"qwen3vl"` to `_HANDLER_MAP` once the upstream class lands. Until then, `LlamaServerVLMEngine` (above) is the unblock path. |
| **`available()` hardening for handler-class-mismatch** | deferred | `engine.py:available()` only checks `handler_name in _HANDLER_MAP`, not whether the class actually exists in the installed `llama_cpp.llama_chat_format` module. Latent footgun for any new handler we add. |
| **`ClaudeVisionEngine` fallback** | deferred (per ADR-0003 Tier 1) | Returns image path reference for Claude's built-in vision instead of running a local VLM. ~1,600 tokens/call (vs ~120 for local VLM). Opt-in `--vision` flag. |
| **SmolVLM2-2.2B** | deferred via `LlamaServerVLMEngine` | Apache 2.0, ~1.1 GB Q4, designed for on-device CPU. No `SmolVLMChatHandler` in `abetlen/llama-cpp-python`; reachable today only via `llama-server`. |

### Rejected

| Candidate | Why not |
|---|---|
| **inferrs** as VLM backend | Text-LLM only; no vision support anywhere in README/features. Verified via WebFetch. |
| **DPT-2 Mini** (Landing AI) | Cloud-only API, English-only, "Preview — do not use in production" status, proprietary. Every axis contradicts cc-voice's local-first positioning. |
| **LFM2-VL-3B** (Liquid AI) | Two blockers: active CPU-only inference bug ([llama.cpp #19184](https://github.com/ggml-org/llama.cpp/issues/19184)) and LFM Open License v1.0 imposes a $10M revenue cap (not Apache 2.0). Revisit only if the bug closes AND the license relaxes. |
| **Moondream3 (preview)** | Business Source License 1.1 — not OSI-compliant; "Additional Use Grant (No Third-Party Service)" clause forbids hosted-service use. No GGUF; transformers-only runtime. |
| **Florence-2** (Microsoft) | Encoder-decoder architecture; not representable in GGUF / not supported by llama.cpp. Would require a parallel runtime (`transformers` or ONNX) and a different `describe()` calling convention (task-based, not chat). Out of scope for the current Protocol. |
| **Apple FastVLM** | Apple Silicon-optimized; primary runtime is MLX, not llama.cpp. No `abetlen/llama-cpp-python` handler. Worth revisiting only if cc-voice adds an `MLXVLMEngine` backend specifically for macOS users. |
| **Phi-4-Multimodal** (Microsoft) | ~14B params; ~9-10 GB at Q4; 12 GB GPU recommended. Too heavy for CPU-only deployment. |

## Cross-subsystem frameworks

### Rejected

These offered to *replace* cc-voice's architecture rather than slot into a single subsystem.

| Candidate | Why not |
|---|---|
| **PersonaPlex** | Scope mismatch — replaces Claude Code's LLM entirely. cc-voice's value prop is "Claude Code does the thinking". Only useful as a future-direction note for the half-duplex → full-duplex frontier (see roadmap "Deferred ideas"). |
| **TEN-framework** (Agora) | Non-OSI clauses on top of Apache 2.0 forbid hosting on end-user devices; daemon-required runtime; bundled STT/TTS are cloud APIs (Deepgram/ElevenLabs). Full-duplex agent framework, not a half-duplex engine — every cc-voice hard constraint violated. |
