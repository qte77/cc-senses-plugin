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

# /see

Capture the screen, run a local vision-language model (Qwen2.5-VL by default via llama-cpp-python), and inject a short text description into Claude's context for Claude to act on. ~120 tokens per call vs ~1,600 if you sent the raw image to Claude's vision API. **No external daemon** — model runs in-process via llama-cpp-python.

## Install — three steps

```bash
# 1. Core scaffolding deps (mss, Pillow, blake3)
make setup_see

# 2. llama-cpp-python (pick ONE matching your hardware)
#    See `make setup_see` output for the exact commands.
#    Examples:
uv pip install 'llama-cpp-python' \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
# or CUDA 12.4:
# uv pip install 'llama-cpp-python' --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
# or Metal:
# CMAKE_ARGS='-DLLAMA_METAL=on' uv pip install llama-cpp-python

# 3. Download the Qwen2.5-VL GGUF + mmproj files
mkdir -p ~/.cache/cc-voice/models
cd ~/.cache/cc-voice/models
wget https://huggingface.co/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
wget https://huggingface.co/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf
```

Then point `[vlm].model_path` and `[vlm].mmproj_path` at the downloaded files. See [`.cc-voice.example.toml`](../../.cc-voice.example.toml) for the full `[vlm]` schema.

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
make plugin_install_local            # registers local marketplace + installs cc-voice (project scope)
make run_cc                          # starts claude; then type /see in the session
make plugin_uninstall                # removes plugin + marketplace when done
```

## Implementation

```bash
python -m cc_vlm $ARGUMENTS
```

## Configuration

See [`.cc-voice.example.toml`](../../.cc-voice.example.toml) `[vlm]` section for the full schema and `CC_VLM_*` env overrides. Supported `handler_name` values are listed in [`docs/architecture.md`](../../docs/architecture.md#supported-vlm-models-llama-cpp-python-handlers).

## Token budget and rationale

For the in-process-VLM-vs-Claude-Vision token comparison and the rationale for picking llama-cpp-python over Ollama, see [`docs/architecture.md`](../../docs/architecture.md#vlm-token-budget) and [`docs/adr/0003-vlm-screen-sharing.md`](../../docs/adr/0003-vlm-screen-sharing.md).

For an end-to-end user flow (feeding screen content to Claude so it can debug or suggest fixes), see [`docs/UserStory.md`](../../docs/UserStory.md#flow-b-feed-screen-content-to-claude) Flow B.

## Removing changes made by `/see`

`/see` is stateless — each call is independent and leaves nothing persistent except the temp JPEG it writes and any cached model files you downloaded for the VLM. To fully remove:

| Artifact | Removal |
|---|---|
| Per-session cache (in-memory `DescribeCache`) | Exits with the Python process. Nothing to clean. |
| Temp JPEGs (`/tmp/tmp*.jpg`) | `make clean_see_artifacts` |
| Downloaded GGUF + mmproj (`~/.cache/cc-voice/models/`) | `make clean_models` |
| Python venv + pytest/ruff caches | `make clean` |
| All of the above at once | `make clean_all` |
| Plugin installation (if done via `make plugin_install_local`) | `make plugin_uninstall` |
| `llama-cpp-python` wheel | `uv pip uninstall llama-cpp-python` (manual since it's not in `[see]` extras) |

There is **no undo for past descriptions** that were injected into a Claude Code conversation — once text is in the conversation it stays in the conversation history. Only future behavior is controllable (via config or by not calling `/see` again).

## Status

Development — functional MVP. Ships `LlamaCppVLMEngine` only. Follow-ups (Ollama backend, Claude Vision opt-in, focused-window crop, auto-template detection, persistent cache) are tracked in the roadmap. See [`docs/adr/0003-vlm-screen-sharing.md`](../../docs/adr/0003-vlm-screen-sharing.md).
