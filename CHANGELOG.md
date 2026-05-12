# Changelog

## [Unreleased]

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
