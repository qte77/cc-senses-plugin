---
name: see
description: Capture the screen and inject a short text summary into Claude's context via an in-process VLM (llama-cpp-python). No daemon. Use to feed terminal/editor/browser state to Claude for debug, fix suggestions, or summarization with minimal token cost.
compatibility: Designed for Claude Code
metadata:
  allowed-tools: Bash, Read, Write
  argument-hint: [--template terminal|editor|browser|gui|generic] [--no-cache] [--save-only]
  context: inline
  stability: development
---

Capture the screen, run a local vision-language model (Moondream2 by default via llama-cpp-python), and inject a short text description into Claude's context for Claude to act on. ~120 tokens per call vs ~1,600 if you sent the raw image to Claude's vision API. **No external daemon** — model runs in-process via llama-cpp-python.

## Install

```bash
make setup_see           # default: Moondream2 (~0.9 GB Q4, fastest CPU)
# or
make setup_see_qwen25    # alt: Qwen2.5-VL-3B (~1.6 GB Q4, richer output)
```

Each target installs `--extra see` deps, downloads the GGUF + mmproj into `~/.cache/cc-senses-bridge/models/`, and prints both the matching `llama-cpp-python` install command (run it manually — hardware-specific) and the `[vlm]` snippet to drop into `.cc-senses.toml`. See [`.cc-senses.example.toml`](../../.cc-senses.example.toml) for the full `[vlm]` schema.

## Usage

- `/see` — capture full screen, describe using the configured template (default: `generic`)
- `/see --template terminal` — constrained to terminal output (most recent command, exit status, errors)
- `/see --template editor` — code editor state (filename, cursor line, diagnostics)
- `/see --template browser` — page title, main heading, banners
- `/see --template gui` — active window, focused element, dialog text
- `/see --template generic` — free-form ≤100-word description
- `/see --no-cache` — bypass frame-hash cache; always call the VLM
- `/see --save-only` — capture + save JPEG, print the path, don't call the VLM
- `/see --monitor N` — capture specific monitor (default 1 = primary)
- `/see --image-file PATH` — describe a pre-captured image instead of capturing the screen. Use for saved screenshots, CI/headless runs, or environments where mss cannot access a display.

## Local testing without Claude Code

Two workflows for dev loops:

**Direct module invocation** (fastest, bypasses CC):

```bash
make see TEMPLATE=terminal           # capture + describe via live VLM
make see_file FILE=shot.jpg          # describe a pre-captured image (no display needed)
make see_save_only                   # capture + save JPEG, print path (no VLM call)
make smoke                           # imports + --help + full test suite
```

**Plugin installed into Claude Code** (full integration, uses CC slash commands):

```bash
make plugin_validate                 # sanity-check the manifest first
make plugin_install_local            # registers local marketplace + installs cc-senses-bridge (project scope)
make run_cc                          # starts claude; then type /see in the session
make plugin_uninstall                # removes plugin + marketplace when done
```

## Implementation

```bash
python -m cc_vlm $ARGUMENTS
```

## Configuration

See [`.cc-senses.example.toml`](../../.cc-senses.example.toml) `[vlm]` section for the full schema and `CC_VLM_*` env overrides. Supported `handler_name` values are listed in [`docs/architecture.md`](../../docs/architecture.md#supported-vlm-models-llama-cpp-python-handlers).

## Token budget and rationale

For the in-process-VLM-vs-Claude-Vision token comparison and the rationale for picking in-process `llama-cpp-python` over external daemons (Ollama, llama-server), see [`docs/architecture.md`](../../docs/architecture.md#vlm-engine-comparison) and [`docs/adr/0003-vlm-screen-sharing.md`](../../docs/adr/0003-vlm-screen-sharing.md).

For an end-to-end user flow (feeding screen content to Claude so it can debug or suggest fixes), see [`docs/UserStory.md`](../../docs/UserStory.md#flow-b-feed-screen-content-to-claude) Flow B.

## Removing changes made by `/see`

`/see` is stateless — each call is independent and leaves nothing persistent except the temp JPEG it writes and any cached model files you downloaded for the VLM. To fully remove:

| Artifact | Removal |
|---|---|
| Per-session cache (in-memory `DescribeCache`) | Exits with the Python process. Nothing to clean. |
| Temp JPEGs (`/tmp/tmp*.jpg`) | `make clean_see_artifacts` |
| Downloaded GGUF + mmproj (`~/.cache/cc-senses-bridge/models/`) | `make clean_models` |
| Python venv + pytest/ruff caches | `make clean` |
| All of the above at once | `make clean_all` |
| Plugin installation (if done via `make plugin_install_local`) | `make plugin_uninstall` |
| `llama-cpp-python` wheel | `uv pip uninstall llama-cpp-python` (manual since it's not in `[see]` extras) |

There is **no undo for past descriptions** that were injected into a Claude Code conversation — once text is in the conversation it stays in the conversation history. Only future behavior is controllable (via config or by not calling `/see` again).

## Status

Development — functional MVP. Ships `LlamaCppVLMEngine` only. Follow-ups (`LlamaServerVLMEngine` HTTP backend, Claude Vision opt-in, focused-window crop, auto-template detection, persistent cache) are tracked in the roadmap. See [`docs/adr/0003-vlm-screen-sharing.md`](../../docs/adr/0003-vlm-screen-sharing.md).
