# ADR-0003: VLM Screen-Sharing for /see Command

**Status**: Accepted (2026-04-11)

## Context

`/see` shares the user's screen with Claude for visual reasoning during
pair programming. Key constraint: token cost per screenshot must be low
enough for frequent interactive use.

## Decision

**Tier 2 (local VLM) as MVP** — `llama-cpp-python` with Qwen2.5-VL-3B
generates a text description (~120 tokens) injected as prompt context.

**Tier 1 (Claude Vision API) deferred** — ~1,600 tokens per raw image.
Token cost is the dominant UX concern for interactive `/see` use.

**Tier 3 (hybrid)** deferred — VLM summary + compressed thumbnail. Most
complex, defer until Tier 2 proves insufficient.

## Rejected

- **inferrs** — text-LLM only, no vision support
- **DPT-2 Mini** — cloud-only, English-only, preview status

## Consequences

- Zero API cost per screenshot (fully local)
- Cold-start ~3-5 s (model load), warm calls ~200-500 ms
- Large model files (1-4 GB) affect first-run experience
- BLAKE3 frame cache eliminates redundant VLM calls

---

## Update (2026-05-13) — what shipped beyond the original decision

The original ADR proposed a single in-process `llama-cpp-python` MVP
with Qwen2.5-VL-3B. Three subsequent changes are worth recording:

- **Default flipped Qwen2.5-VL-3B → Moondream2** (v0.7.0, #91).
  Moondream2 Q4 is ~0.9 GB vs Qwen2.5-VL-3B's ~1.6 GB and faster on
  CPU. Qwen2.5-VL stays available via `make setup_see_qwen25`.
- **`LlamaServerVLMEngine` HTTP backend shipped** (v0.9.0, #108).
  Same `llama.cpp` binary as the in-process path, but as a long-lived
  daemon — routes around the `abetlen/llama-cpp-python` chat-handler
  gap (unlocks SmolVLM2 + Qwen3-VL today) AND fixes the false-warm
  problem: `/see` invokes a fresh Python process per call, so the
  in-process engine never actually runs hot across CLI invocations.
- **Three lifecycle modes** (v0.9.0, #110 + #111): user-managed,
  lazy auto-spawn (default), and SessionStart preload. `cc_vlm.server_manager`
  owns spawn / pidfile / health-probe / shutdown.

**Tier 1 (Claude Vision API)** remains deferred — no demand surfaced.
**Tier 3 (hybrid)** also deferred — Tier 2 has proven sufficient with
the lifecycle additions.

See [`docs/architecture.md` § VLM Pipeline](../architecture.md#vlm-pipeline)
for the current state of all of this.
