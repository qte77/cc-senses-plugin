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

## Engines

Two engines are available; auto-detect picks the first one that's configured.

| Engine | When to use | Tradeoff |
|---|---|---|
| `llamacpp` (in-process) | You have `model_path` + `mmproj_path` set and the appropriate `llama-cpp-python` chat handler exists for your model family | No daemon; reloads the model on every `/see` call (each invocation is a fresh Python process) |
| `llamaserver` (HTTP) | You want a hot model across `/see` calls, or you're using SmolVLM2 / Qwen3-VL where the in-process handler doesn't exist yet | User runs `llama-server` separately; ~1-2 GB RAM while alive; warm response within 200-500 ms |

### Using the llama-server backend

Three operating modes, picked by config. Useful for SmolVLM2-2.2B, Qwen3-VL-2B, or any GGUF llama.cpp supports but `llama-cpp-python` doesn't yet.

Prerequisite: `llama-server` must be installed and on your `PATH` (install via your distro's `llama.cpp` package or build from source).

#### 1. Lazy auto-spawn (default)

cc-senses-bridge spawns `llama-server` on first `/see`, then re-uses the warm process for subsequent calls. Set in `.cc-senses.toml`:

```toml
[vlm]
engine = "llamaserver"
server_url = "http://localhost:8080"
model_path = "/path/to/SmolVLM2.gguf"
mmproj_path = "/path/to/SmolVLM2-mmproj.gguf"
# auto_spawn defaults to true
```

First `/see` call takes up to ~30 s (model load). Subsequent calls are warm (~200-500 ms). Inspect/stop the spawned server:

```bash
make vlm_server_status   # is it running?
make vlm_server_logs     # tail the boot log
make vlm_server_stop     # SIGTERM the spawned process
```

#### 2. User-managed

You start `llama-server` yourself; cc-senses-bridge just POSTs to it. Useful for shared servers, GPU rigs, or remote hosts.

```bash
llama-server -m /path/to/model.gguf --mmproj /path/to/mmproj.gguf --port 8080
```

```toml
[vlm]
engine = "llamaserver"
server_url = "http://localhost:8080"
auto_spawn = false   # cc-senses-bridge will NOT try to spawn
```

For remote hosts (`server_url = "http://my-rig.local:8080"`), `auto_spawn` is implicitly disabled — only localhost / 127.0.0.1 / ::1 are eligible for auto-spawn.

#### 3. Preload

Spawns `llama-server` at Claude Code session start so even the first `/see` is hot. Set in `.cc-senses.toml`:

```toml
[vlm]
engine = "llamaserver"
model_path = "/path/to/model.gguf"
mmproj_path = "/path/to/mmproj.gguf"
preload = true
```

When the CC session starts, the SessionStart hook (`cc-vlm-preload`) spawns `llama-server` in a detached background process. By the time you type `/see` for the first time, the model is already loaded and the first call is warm (~200-500 ms). Trade-off: ~1-2 GB RAM is held for the entire session, even if `/see` is never used. Turn preload off for sessions where you don't expect to use vision.

```bash
make vlm_server_status   # verify the server came up
make vlm_server_logs     # inspect boot output if it didn't
make vlm_server_stop     # manually stop the daemon mid-session
```

The SessionEnd hook (`cc-vlm-shutdown`) terminates the spawned server automatically when the CC session closes. If CC crashes, the daemon may persist — `make vlm_server_status` catches that, `make vlm_server_stop` cleans it up.

### Known limitations

- **Cold-start concurrency race**: parallel `/see` invocations during the very first call (when the server is being spawned) may produce a transient EADDRINUSE on the losing process's `llama-server` spawn. The system self-heals on the next invocation — `pid_is_alive` detects the dead PID and re-spawns. No file lock for now (YAGNI for interactive CLI use).
- **30 s spawn timeout**: if the model is large or disk is cold, `available()` can time out waiting for `/health`. Check `make vlm_server_logs` for boot errors.

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
