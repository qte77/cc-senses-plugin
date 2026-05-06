# User Stories

End-to-end flows showing how cc-voice fits into a real working session.
For the full configuration schema, see [`.cc-voice.example.toml`](../.cc-voice.example.toml).
For pipeline and engine details, see [architecture.md](architecture.md).

## Personas

- **Solo dev pair-programming aloud** — wants to hear Claude's
  responses while typing or reading code, occasionally speaking back
  for hands-free input.
- **Dev who wants Claude to act on screen content** — feeds the
  current terminal/editor/browser state into Claude's context as
  text, so Claude can debug, suggest fixes, or summarize — without
  paying raw-vision token costs and without manually copy-pasting.
- **Accessibility user** — relies on bidirectional voice as the
  primary interaction channel; full Voice Loop must be reliable, not
  just demo-quality.

## Flow A: Voice Loop

Goal: speak prompts, hear answers, no typing.

Steps:

1. `/speak --toggle` — enables Stop-hook auto-read so every response
   is spoken once it completes.
2. `/voice` — enables Claude Code's built-in mic input.
3. Speak a prompt → Claude transcribes → answers in text → cc-voice
   reads the answer aloud.

Minimal config (in `.cc-voice.toml`):

```toml
auto_read = true
[stt]
auto_listen = true
```

The Stop hook splits the response into sentences via `SentenceBuffer`
so audio starts ~1 s after the response completes, not at the end.

## Flow B: Feed screen content to Claude

Goal: inject the current screen state into Claude's context as text
so Claude can act on it (debug, suggest a fix, summarize), without
copy-pasting manually.

Two paths exist:

- **Claude Code's native image analysis** — send the raw screenshot;
  ~1,600 tokens per call. Best fidelity, but expensive at any
  reasonable update cadence.
- **Local VLM/OCR** — run a small vision-language model (or OCR) on
  device to extract a short text summary; ~120 tokens per call. Lower
  fidelity, but cheap enough to use repeatedly.

cc-voice's `/see` uses the local path by default.

Steps:

1. `/see --template terminal` — captures the active monitor, runs the
   local VLM (default Moondream2 via llama-cpp-python) entirely
   on-device, and injects the short text description into Claude's
   prompt.
2. Claude reads that text alongside the rest of the conversation and
   responds — e.g., explains a stack trace, proposes a code fix,
   summarizes editor state.
3. Iterate: change the screen → re-run `/see`. Cache hits on
   identical frames cost 0 tokens.
4. Pick a template that matches what's on screen — narrows the VLM's
   output and keeps injected context small:
   - `--template editor` — filename, cursor line, diagnostics
   - `--template browser` — page title, main heading, banners
   - `--template gui` — active window, focused element, dialog text
   - `--template generic` — free-form ≤100-word description

Minimal config (run `make setup_see` to populate the paths):

```toml
[vlm]
model_path = "/home/USER/.cache/cc-voice/models/moondream2-text-model-f16_ct-q4_0.gguf"
mmproj_path = "/home/USER/.cache/cc-voice/models/moondream2-mmproj-f16.gguf"
handler_name = "moondream"
```

See [`docs/adr/0003-vlm-screen-sharing.md`](adr/0003-vlm-screen-sharing.md)
for the rationale behind the in-process VLM choice.

## Flow C: Hotkey-stopped playback

Goal: silence audio instantly when interrupted, without killing the
shell or REPL.

```bash
uv run cc-tts --stop
```

Reads the PID file at `~/.cache/cc-voice/speak.pid` and SIGTERMs the
whole process group. Works for all delivery modes (Stop hook,
stream-json, PTY proxy) — every mode writes the pidfile on start.

Bind to a hotkey (no code change). Pick a key not already used by
your shell/editor — common available choices: Alt+s, F8, Ctrl+\\.

```bash
# bash — Alt+s (\es)
bind -x '"\es":"uv run cc-tts --stop"'

# zsh — Alt+s
cc-tts-stop() { uv run cc-tts --stop }
zle -N cc-tts-stop
bindkey '^[s' cc-tts-stop

# tmux — prefix + s (or global with -n)
bind-key s run-shell "uv run cc-tts --stop"
```

Avoid Ctrl+G (nano help), Ctrl+C (SIGINT), Ctrl+D (EOF), Ctrl+Z (suspend).
