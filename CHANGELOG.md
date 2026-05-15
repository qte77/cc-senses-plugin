# Changelog

## [Unreleased]

## [0.10.1] - 2026-05-15

### Fixed

- All four `setup_see` / `setup_see_qwen25` URLs were dead: `ggml-org/moondream2-20250414-GGUF` never shipped the `f16_ct-q4_0.gguf` filename the Makefile asked for (only `f16_ct-vicuna` and `mmproj-f16-20250414`), and `bartowski/Qwen2.5-VL-3B-Instruct-GGUF` was removed entirely. Repointed at canonical author repos: `moondream/moondream2-gguf` (F16 only — no Q4 published at canonical source) and `lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF` (Q4_K_M).

### Changed

- VLM model registry pivoted to `src/cc_vlm/models.toml` + `python -m cc_vlm.setup_models <key>`. URL constants and filename literals no longer live in the Makefile — filenames are derived from URL basenames by construction, so the drift class of bug that caused the v0.10.0 dead URLs is structurally impossible going forward. Make recipes collapsed from 66 lines of shell to 12 lines of one-liners.

### Added

- `make setup_see_qwen3vl` — llamaserver opt-in target for Qwen3-VL-2B (official Qwen, apache-2.0, ~1.55 GB Q4_K_M text + Q8 mmproj). Reachable through `LlamaServerVLMEngine` without waiting on `abetlen/llama-cpp-python` to ship a `Qwen3VLChatHandler`.
- `make setup_see_smolvlm` — llamaserver opt-in target for SmolVLM-500M (ggml-org, apache-2.0, 546 MB total). The "fits-on-anything" tier for low-spec laptops.
- `make setup_default_all` — kitchen-sink: dev tools + all TTS engines + STT + the in-process default `/see` tier (Moondream2).
- `src/cc_vlm/setup_models.py` — TOML-driven loader, downloader, and engine-aware `[vlm]` snippet emitter with platform-aware llama-cpp-python / llama-server install hints.

### Migration notes

- Re-run `make setup_see` (or `make clean_models && make setup_see`) to fetch the new, working Moondream2 GGUFs. Model files have new basenames: `moondream2-text-model-f16.gguf` (was `f16_ct-q4_0.gguf`) and `moondream2-mmproj-f16.gguf` (unchanged).
- Existing `.cc-senses.toml` files keep working — config schema is unchanged. Only the `model_path` / `mmproj_path` values need to point at the new filenames if you reuse the installer's printed snippet.

## [0.10.0] - 2026-05-13

### Changed

- chore: rename plugin slug `cc-senses-bridge` → `cc-senses-plugin` to align with the canonical GitHub repo name (renamed 2026-05-13). Touches `plugin.json`, `marketplace.json`, `pyproject.toml`, all source identifier strings, Makefile recipe descriptions, docs, README, and the `~/.cache/cc-senses-bridge/` → `~/.cache/cc-senses-plugin/` cache directory paths. Python module names (`cc_tts`, `cc_stt`, `cc_vlm`, `cc_voice_common`) and the config file (`.cc-senses.toml`) are intentionally preserved — the "senses" stem stays recognizable and avoids forcing users through another config-file migration.

### Migration notes

- Move cached VLM models: `mv ~/.cache/cc-senses-bridge ~/.cache/cc-senses-plugin` (or re-run `make setup_see` to re-download)
- Reinstall the plugin: `make plugin_uninstall && make plugin_install_local`
- Install command changes to `claude plugin install cc-senses-plugin@cc-senses-plugin`
- `.cc-senses.toml` filename is unchanged; only the header comment was updated

## [0.9.0] - 2026-05-13

### Added

- feat(vlm): `LlamaServerVLMEngine` HTTP backend — talks to `llama-server` via OpenAI-compatible API. Routes around the `abetlen/llama-cpp-python` chat-handler gap; unlocks SmolVLM2-2.2B and Qwen3-VL-2B today. (#108)
- feat(vlm): `cc_vlm.server_manager` module — spawn / pidfile / health-probe / shutdown lifecycle helpers for the HTTP backend. (#110)
- feat(vlm): lazy auto-spawn — `auto_spawn = true` (default) makes the first `/see` invocation spawn `llama-server` automatically when no daemon is reachable; subsequent calls are warm. (#110)
- feat(vlm): SessionStart preload hook + SessionEnd shutdown hook — opt-in `preload = true` spawns `llama-server` in the background at CC session start so even the first `/see` is hot.
- build(make): `vlm_server_status` / `vlm_server_stop` / `vlm_server_logs` targets for manual lifecycle control.
- pyproject entry points: `cc-vlm-preload` (SessionStart target), `cc-vlm-shutdown` (SessionEnd target).
- Six new `[vlm]` config fields: `server_url`, `server_model_alias`, `server_port`, `server_binary`, `auto_spawn`, `preload`.
- `httpx>=0.27` added to `[see]` extras.

### Migration notes

- New `[vlm]` engine: set `engine = "llamaserver"` plus `model_path`/`mmproj_path` to use the HTTP backend. With `auto_spawn = true` (default) cc-senses-bridge starts `llama-server` itself. With `auto_spawn = false`, run `llama-server` manually.
- `preload = true` is opt-in; default is `false`. Enable per `.cc-senses.toml` if you want the model warm from session start (costs ~1-2 GB RAM for the session lifetime).
- Existing in-process (`llamacpp`) workflow unchanged.

## [0.8.0] - 2026-05-12

### Changed

- chore: rename project `cc-voice` → `cc-senses-bridge` to reflect multimodal scope (TTS + STT + VLM). Config file renamed `.cc-voice.toml` → `.cc-senses.toml`; cache directory `~/.cache/cc-voice/` → `~/.cache/cc-senses-bridge/`; plugin slug renamed across `plugin.json`, `marketplace.json`, install commands, and docs. Python module names (`cc_tts`, `cc_stt`, `cc_vlm`, `cc_voice_common`) kept as-is to avoid import churn.

### Migration notes

- Move existing `.cc-voice.toml` to `.cc-senses.toml`
- Move cached VLM models from `~/.cache/cc-voice/models/` to `~/.cache/cc-senses-bridge/models/`, or re-run `make setup_see`
- Reinstall plugin: `make plugin_uninstall && make plugin_install_local`

## [0.7.0] - 2026-05-08

### Added

- docs: `docs/UserStory.md` — three end-to-end flows + personas (#83)
- feat(vlm): `make setup_see` / `setup_see_qwen25` targets — guided VLM install with hardware detection; download URLs centralized in Makefile vars (#91)
- docs: `docs/landscape.md` — engine/model evaluation matrix (single source of truth for shipped / deferred / rejected per subsystem)

### Changed

- feat(vlm): default VLM handler flips `qwen2.5vl` → `moondream` (Qwen2.5-VL stays available as alt) (#91)
- docs: dedupe config schema — `.cc-voice.example.toml` is canonical; README + `skills/*/SKILL.md` link to it (#83, #87, closes #60)
- docs(roadmap): mark v0.5.0/v0.6.0 as shipped; trim closed-issue noise (#81)
- docs(skills): drop redundant H1 from each `skills/*/SKILL.md` — title lives in YAML frontmatter (#94)

### Fixed

- fix(vlm): "No VLM engine available" `RuntimeError` points at `make setup_see` instead of an inline HF URL (#91)
- fix(config): wrap TTS keys in `[tts]` section in `.cc-voice.example.toml` (#83)
- fix(readme): Link Checker badge URL repointed at `lint-md-links.yml` (was 404 on missing workflow) (#93)

### Removed

- chore: orphan `scripts/debug_pty_capture.py` — parent feature (PTY proxy) is parked (#84, closes #56 line item)

### Tests

- test(speak): `--stop` and `--stream` coverage — pidfile lifecycle, SIGTERM dispatch, streaming flag routing (#88, closes #56 line item)

### Internal

- chore: gitignore phantom `/.mcp.json` (sandbox char-device) and `.env` (per-machine secrets) (#82)

## [0.6.0] - 2026-04-23

### Added

- feat(stt): token optimization for `/listen` — `strip_fillers()`, `match_intent()`, `cap_words()` preprocessors wired into live pipeline; matched intents skip LLM entirely (#29)
- feat(stt): `strip_fillers`, `intent_match`, `max_words` config fields in `[stt]` section (#29)
- feat(repl): streaming sentence-by-sentence TTS during generation via `_SentenceBuffer` + queue worker (#56)
- feat(repl): "thinking..." indicator between send and first response delta (#56)
- feat(repl): tool-use event rendering — displays `[tool_name]` during tool calls (#56)
- feat(gha): bump helper scripts (`create_pr.sh`, `delete_branch_pr_tag.sh`) with DRY_RUN support (#72)
- docs: CONTRIBUTING.md — setup, workflow, commit conventions (#56)
- test: 25 new STT tests (preprocess + intents) and 24 BATS tests for bump scripts (#29, #72)

### Changed

- refactor(config): migrate TTS, STT, VLM configs from dataclass + manual env overrides to pydantic `BaseSettings` with `env_prefix`; shared `cc_voice_common.config` module replaces 3 copies of `_find_config_file()` — net −85 LOC (#39)
- fix(repl): Ctrl+C stops TTS playback instead of killing REPL; second press within 1s exits (#56)
- fix(gha): bump workflow creates PR from ephemeral branch instead of pushing directly to protected main (#72)
- fix: replace LICENSE with canonical Apache 2.0 text (GitHub license detection) + add NOTICE (#70)
- chore: enable `gha-dev` plugin for BATS + GHA skill access (#73)

### Dependencies

- add `pydantic-settings>=2.9.1` (config migration) (#39)

## [0.5.0] - 2026-04-11

### Added

- feat(see): `cc_vlm` module with in-process `llama-cpp-python` backend — `/see` skill captures screen, runs a local VLM (Qwen2.5-VL default) with task-constrained prompt templates, returns a text description for Claude's prompt. ~120 tokens/call vs ~1,600 for raw vision (~13× reduction); 0 tokens on cache hits via BLAKE3 frame hash LRU. (#26)
- feat(see): `--image-file PATH` flag — describe a pre-captured image instead of capturing the screen; enables headless testing and saved-screenshot use cases. (#26)
- feat(see): five task-constrained prompt templates (terminal, editor, browser, gui, generic) capping VLM output length at the source. (#26)
- feat(see): `LlamaCppVLMEngine` supporting six model families via `_HANDLER_MAP` (qwen2.5vl, llava15, llava16, moondream, minicpmv, nanollava). (#26)
- build(make): `setup_user` target — end-user minimum install (package + best local TTS), no dev tools. `setup_all` clarified as "Developer happy path". (#28)
- build(make): `setup_see` target — installs `[see]` extras (mss, Pillow, blake3) and prints hardware-specific `llama-cpp-python` install commands (CPU / CUDA / Metal / ROCm). (#26)
- build(make): `plugin_validate`, `plugin_install_local`, `plugin_uninstall`, `plugin_list`, `run_cc` targets — full plugin-in-CC lifecycle for local dev. (#26)
- build(make): `smoke_imports`, `smoke_cli`, `smoke` targets — fast sanity checks that don't need external deps. (#26)
- build(make): `listen`, `see`, `see_file`, `see_save_only` direct-run targets (bypass CC for testing). (#26)
- build(make): `clean_models`, `clean_see_artifacts`, `clean_all` targets — remove downloaded VLM models, `/tmp` JPEGs, and full local reset. (#26)
- docs(roadmap): `docs/roadmap/v0.5.x.md` — living tracker for deferred ideas and rejected directions alongside filed issues. (#35)

### Changed

- fix(types): narrow `listen.py` config parameter to `STTConfig | None` (was `object`) — eliminates pyright strict errors without per-line suppressions. (#26)
- fix(stt): add `argparse` to `cc_stt/__main__.py` — `python -m cc_stt --help` now works; previously jumped straight to `listen_live()` and errored. Backward compat preserved for `python -m cc_stt hook` and file transcription. (#26)
- chore(build): `[project.optional-dependencies] all` now uses PEP 621 self-references (`cc-voice[piper]`, etc.) instead of duplicating every dep — fixed long-standing DRY violation. (#26)

## [0.4.0] - 2026-04-11

### Added

- feat(stt): live `/listen` pipeline — mic capture → VAD buffering → Moonshine/Vosk transcription → PTY injection (#14)
- feat(stt): file transcription mode via `transcribe_file()` (#14)
- feat(stt): `__main__.py` dispatcher routing to listen/transcribe/hook modes (#14)
- docs(vlm): ADR-0001 screen-sharing architecture for `/see` — three tiers (CC-native vision, local VLM, hybrid) (#18)
- docs(vlm): `/see` skill stub (status: research) (#18)
- build(make): `setup_all` happy-path target installing dev + TTS engines + STT deps (#19)
- build(make): `setup_stt` target using existing `[stt]` extras group (#19)
- build(make): `clean` target removing `.venv` + caches (#19)
- test: 9 listen pipeline tests — TestListenLive, TestTranscribeFile, TestMainDispatch (#14)
- test: 19 plugin config validation tests — plugin.json schema, marketplace source resolution (#13)

### Changed

- fix(types): adopt pyright strict + suppress-unknowns config — resolves untyped-library leakage from sounddevice / pydantic-settings; ported from sibling project Agents-eval (#19)
- fix(types): narrow `listen.py` config parameter to `STTConfig | None` instead of `object` (#14)
- chore(build): Makefile uses `uv sync` only — dropped `uv pip install` rule violations in `setup` and `setup_dev` (#19)
- chore(build): rename `setup_tts` → `setup_espeak` for accuracy (it installs espeak-ng + mpv, not TTS generically) (#19)
- chore(build): `test_coverage` now reports both `cc_tts` and `cc_stt` — previously silently dropped `cc_stt` (#19)
- chore(build): `wrap` help text now warns about bwrap sandbox deadlock per AGENT_LEARNINGS.md (#19)
- chore(gitignore): exclude `.coverage` artifact (#25)
- style: ruff format drift cleanup across 5 files (src/cc_stt/mic.py, test_plugin_config.py, test_stt_config.py, test_stt_engine.py, test_stt_mic.py) (#25)
- build(deps-dev): bump edge-tts ≥6.1.0 → ≥7.2.8 (#20)
- build(deps-dev): bump bump-my-version ≥0.29.0 → ≥1.3.0 (#21)

### Fixed

- fix: plugin discovery — changed marketplace source from relative path to github source type (#7)
- fix: suppress CodeFactor B607/B108 warnings (#11)

## [0.3.0] - 2026-04-04

### Added

- `cc_stt` module with STTEngine protocol (Moonshine, Vosk) and auto-detection
- `STTConfig` with `.cc-voice.toml` [stt] section and `CC_STT_*` env overrides
- `MicCapture` with sounddevice streaming and `NoMicrophoneError` graceful degradation
- `UtteranceBuffer` with energy-based VAD, silence boundary detection, max duration timeout
- `inject_text()` PTY input for STT-to-stdin pipeline
- `should_auto_listen()` hook handler with graceful error fallback
- `/listen` skill definition (planned: live listen pipeline)
- 47 new tests (113 total) covering all STT modules
- `sounddevice>=0.5.0` as optional `stt` dependency

## [0.2.0] - 2026-04-04

### Changed

- Renamed from cc-tts to cc-voice (end-to-end voice scope)
- Config file: `.cc-voice.toml` (reads legacy `.cc-tts.toml` as fallback)
- Plugin name: `cc-voice` in plugin.json and marketplace.json

## [0.1.0] - 2026-04-04

### Added

- PTY proxy for live streaming TTS (`cc-tts-wrap`) with sentence-chunked pipeline
- Stream filter: ANSI stripping, code block skip, spinner suppress, tool output skip
- Sentence buffer with boundary detection and flush callback
- TTS engine abstraction with Kokoro, Piper, espeak-ng support and auto-detection
- Model auto-download for Piper (HuggingFace) and Kokoro (GitHub releases)
- Audio player with mpv/ffplay/aplay fallback chain and no-audio-device handling
- Text preprocessor: markdown, code blocks, URLs stripped for clean speech
- Stop hook handler for batch auto-read mode (`hooks/hooks.json`)
- `/speak` skill for on-demand TTS in Claude Code
- Configuration via `.cc-tts.toml` with environment variable overrides
- CC plugin manifest with marketplace.json for local install
- Audio examples comparing espeak-ng, Piper, and Kokoro engines (`assets/audio/`)
- Makefile with quiet-by-default validation (ruff, pyright strict, pytest)
- CI: CodeQL, Dependabot, lychee link checker
- Apache-2.0 license
- 65 tests covering all modules
