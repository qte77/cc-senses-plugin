.SILENT:
.ONESHELL:
.PHONY: \
	setup setup_dev setup_espeak setup_piper setup_kokoro setup_stt \
	setup_see setup_see_qwen25 setup_user setup_all \
	clean validate lint_fix quick_validate lint_src lint_tests lint_md lint_links \
	type_check test test_coverage speak wrap \
	bump_patch bump_minor bump_major help
.DEFAULT_GOAL := help

# -- quiet mode (default: quiet; set VERBOSE=1 for full output) --
VERBOSE ?=
ifndef VERBOSE
  RUFF_QUIET   := --quiet
  PYTEST_QUIET := -q --tb=short --no-header
  COV_QUIET    := --cov-report=
endif

# -- VLM model + llama-cpp-python wheel URLs (single source of truth) --
# Update these vars when bumping recommended models or wheel index URLs.
VLM_MODELS_DIR          := $(HOME)/.cache/cc-senses-bridge/models
VLM_MOONDREAM_MODEL_URL := https://huggingface.co/ggml-org/moondream2-20250414-GGUF/resolve/main/moondream2-text-model-f16_ct-q4_0.gguf
VLM_MOONDREAM_MMPROJ_URL := https://huggingface.co/ggml-org/moondream2-20250414-GGUF/resolve/main/moondream2-mmproj-f16.gguf
VLM_QWEN25_MODEL_URL    := https://huggingface.co/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
VLM_QWEN25_MMPROJ_URL   := https://huggingface.co/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf
LLAMA_CPP_INDEX_CPU     := https://abetlen.github.io/llama-cpp-python/whl/cpu
LLAMA_CPP_INDEX_CUDA124 := https://abetlen.github.io/llama-cpp-python/whl/cu124


# MARK: SETUP


setup: ## Install cc-senses-bridge package (frozen lockfile)
	uv sync --frozen

setup_dev: ## Install with dev + test deps + all extras
	uv sync --all-extras

setup_espeak: ## Install espeak-ng + mpv (minimal, robotic TTS fallback)
	@if command -v dnf > /dev/null 2>&1; then \
		sudo dnf install -y espeak-ng mpv; \
	elif command -v apt-get > /dev/null 2>&1; then \
		sudo apt-get update -qq && sudo apt-get install -y -qq espeak-ng mpv; \
	elif command -v pacman > /dev/null 2>&1; then \
		sudo pacman -S --noconfirm espeak-ng mpv; \
	elif command -v brew > /dev/null 2>&1; then \
		brew install espeak-ng mpv; \
	else \
		echo "No supported package manager found (dnf, apt-get, pacman, brew)" >&2; exit 1; \
	fi

setup_piper: ## Install Piper TTS (neural, good quality, ~60MB model)
	uv sync --extra piper

setup_kokoro: ## Install Kokoro TTS (best local quality, ~82MB model)
	uv tool install git+https://github.com/nazdridoy/kokoro-tts

setup_stt: ## Install STT deps (sounddevice + default engine)
	uv sync --extra stt

setup_see: ## Install /see deps + download Moondream2 (recommended default VLM)
	uv sync --extra see
	mkdir -p $(VLM_MODELS_DIR)
	model=$(VLM_MODELS_DIR)/moondream2-text-model-f16_ct-q4_0.gguf
	mmproj=$(VLM_MODELS_DIR)/moondream2-mmproj-f16.gguf
	if [ ! -f $$model ]; then
		echo "Downloading Moondream2 model ..."
		curl -fL --retry 3 -o $$model $(VLM_MOONDREAM_MODEL_URL)
	else
		echo "Moondream2 model already present — skipping."
	fi
	if [ ! -f $$mmproj ]; then
		echo "Downloading Moondream2 mmproj ..."
		curl -fL --retry 3 -o $$mmproj $(VLM_MOONDREAM_MMPROJ_URL)
	else
		echo "Moondream2 mmproj already present — skipping."
	fi
	echo ""
	echo "  Now install llama-cpp-python for your hardware (NOT auto-installed):"
	if [ "$$(uname -s)" = "Darwin" ]; then
		echo "    CMAKE_ARGS='-DLLAMA_METAL=on' uv pip install llama-cpp-python    # macOS Metal"
	elif command -v nvidia-smi > /dev/null 2>&1; then
		echo "    uv pip install llama-cpp-python --extra-index-url $(LLAMA_CPP_INDEX_CUDA124)    # CUDA 12.4 detected"
	else
		echo "    uv pip install llama-cpp-python --extra-index-url $(LLAMA_CPP_INDEX_CPU)    # CPU"
	fi
	echo ""
	echo "  Then add this to .cc-senses.toml:"
	echo ""
	echo "    [vlm]"
	echo "    model_path = \"$$model\""
	echo "    mmproj_path = \"$$mmproj\""
	echo "    handler_name = \"moondream\""

setup_see_qwen25: ## Install /see deps + download Qwen2.5-VL-3B (alt VLM, richer output)
	uv sync --extra see
	mkdir -p $(VLM_MODELS_DIR)
	model=$(VLM_MODELS_DIR)/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
	mmproj=$(VLM_MODELS_DIR)/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf
	if [ ! -f $$model ]; then
		echo "Downloading Qwen2.5-VL-3B model ..."
		curl -fL --retry 3 -o $$model $(VLM_QWEN25_MODEL_URL)
	else
		echo "Qwen2.5-VL-3B model already present — skipping."
	fi
	if [ ! -f $$mmproj ]; then
		echo "Downloading Qwen2.5-VL-3B mmproj ..."
		curl -fL --retry 3 -o $$mmproj $(VLM_QWEN25_MMPROJ_URL)
	else
		echo "Qwen2.5-VL-3B mmproj already present — skipping."
	fi
	echo ""
	echo "  Then add this to .cc-senses.toml:"
	echo ""
	echo "    [vlm]"
	echo "    model_path = \"$$model\""
	echo "    mmproj_path = \"$$mmproj\""
	echo "    handler_name = \"qwen2.5vl\""

setup_user: setup setup_kokoro ## End user minimum: package + best local TTS (no dev tools)
	@echo ""
	@echo "  ✓ cc-senses-bridge ready for /speak via Kokoro."
	@echo "  Try: cc-tts 'hello from claude code'"
	@echo ""
	@echo "  Opt-in for more:"
	@echo "    make setup_stt          # /listen dependencies (sounddevice + default STT engine)"
	@echo "    make setup_piper        # alternative TTS (neural VITS, ~60MB)"
	@echo "    make setup_espeak       # minimal TTS fallback (robotic, zero-config)"
	@echo "    skills/see/SKILL.md     # /see install guide (llama-cpp-python + GGUF models)"

setup_all: setup_dev setup_espeak setup_piper setup_kokoro setup_stt ## Developer happy path: dev tools + all TTS + STT
	@echo ""
	@echo "✓ cc-senses-bridge ready."
	@echo "  Try: cc-tts 'hello from claude code'"
	@echo "  Then in Claude Code: /speak --toggle"

clean: ## Remove venv + caches (preserves downloaded TTS/STT/VLM models)
	rm -rf .venv .pytest_cache .ruff_cache .coverage

clean_models: ## Remove downloaded VLM models (~/.cache/cc-senses-bridge/models/)
	@echo "Removing $$HOME/.cache/cc-senses-bridge/models/ ..."
	@rm -rf $$HOME/.cache/cc-senses-bridge/models

clean_see_artifacts: ## Remove /tmp JPEG artifacts produced by cc_vlm --save-only
	@echo "Removing /tmp JPEG captures ..."
	@rm -f /tmp/tmp*.jpg 2>/dev/null || true

clean_all: clean clean_models clean_see_artifacts ## Remove venv + caches + models + temp artifacts (full local reset)
	@echo ""
	@echo "  All cc-senses-bridge local artifacts removed."
	@echo "  For Claude Code plugin removal also run: make plugin_uninstall"


# MARK: VALIDATION


validate: lint_src lint_tests type_check test ## Full validation (lint + type + test)
	echo "--- validate: all passed"

quick_validate: lint_src type_check ## Fast validation (lint + type)
	echo "--- quick_validate: passed"

lint_fix: ## Auto-fix lint and format issues
	echo "--- lint_fix"
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

lint_src: ## Lint and format src with ruff
	echo "--- lint_src$(if $(RUFF_QUIET), [quiet])"
	uv run ruff format --check $(RUFF_QUIET) src/
	uv run ruff check $(RUFF_QUIET) src/

lint_tests: ## Lint and format tests with ruff
	echo "--- lint_tests$(if $(RUFF_QUIET), [quiet])"
	uv run ruff format --check $(RUFF_QUIET) tests/
	uv run ruff check $(RUFF_QUIET) tests/

lint_md: ## Lint markdown files
	echo "--- lint_md"
	markdownlint '*.md' 'assets/**/*.md' '.claude/**/*.md' --fix

lint_links: ## Check for broken links with lychee
	echo "--- lint_links"
	if command -v lychee > /dev/null 2>&1; then
		lychee '*.md' 'assets/**/*.md' '.claude/**/*.md'
	else
		echo "lychee not installed — skipping"
	fi

type_check: ## Run pyright type checker
	echo "--- type_check"
	uv run pyright src/

test: ## Run pytest
	echo "--- test$(if $(PYTEST_QUIET), [quiet])"
	uv run pytest $(PYTEST_QUIET)

test_coverage: ## Run pytest with coverage (cc_tts + cc_stt)
	echo "--- test_coverage"
	uv run pytest --cov=cc_tts --cov=cc_stt --cov-report=term-missing $(COV_QUIET)


# MARK: RUN


speak: ## Run /speak directly (bypasses CC): make speak TEXT="hello"
	uv run python -m cc_tts.speak $(TEXT)

wrap: ## Wrap command with live TTS (may deadlock under bwrap — see AGENT_LEARNINGS.md)
	uv run python -m cc_tts.pty_proxy $(CMD)

listen: ## Run /listen directly (bypasses CC): make listen [FILE=recording.wav] (default: live mic)
	uv run python -m cc_stt $(FILE)

see: ## Run /see directly (bypasses CC): make see [TEMPLATE=terminal]
	uv run python -m cc_vlm $(if $(TEMPLATE),--template $(TEMPLATE),)

see_file: ## Describe a pre-captured image, no screen capture: make see_file FILE=img.jpg [TEMPLATE=generic]
	uv run python -m cc_vlm --image-file $(FILE) $(if $(TEMPLATE),--template $(TEMPLATE),)

see_save_only: ## Capture screen + save JPEG, print path (smoke-test mss + processor, no VLM call)
	uv run python -m cc_vlm --save-only


# MARK: SMOKE


smoke_imports: ## Smoke: verify all cc_* modules import cleanly (no external deps)
	@echo "--- cc_tts imports"
	@uv run python -c "import cc_tts.speak, cc_tts.engine, cc_tts.config; print('  ok')"
	@echo "--- cc_stt imports"
	@uv run python -c "import cc_stt.engine, cc_stt.config, cc_stt.listen; print('  ok')"
	@echo "--- cc_vlm imports"
	@uv run python -c "import cc_vlm.engine, cc_vlm.config, cc_vlm.capture, cc_vlm.processor, cc_vlm.templates, cc_vlm.cache; print('  ok')"

smoke_cli: ## Smoke: verify each module's --help works
	@echo "--- cc_tts.speak --help"
	@uv run python -m cc_tts.speak --help > /dev/null && echo "  ok"
	@echo "--- cc_stt --help"
	@uv run python -m cc_stt --help > /dev/null && echo "  ok"
	@echo "--- cc_vlm --help"
	@uv run python -m cc_vlm --help > /dev/null && echo "  ok"

smoke: smoke_imports smoke_cli test ## Full smoke: imports + CLIs + test suite
	@echo ""
	@echo "  ✓ smoke test passed"


# MARK: PLUGIN


plugin_validate: ## Validate the local plugin manifest without installing
	claude plugin validate .

plugin_install_local: ## Install cc-senses-bridge from the local working tree (project scope)
	@echo "Registering local repo as a project-scope marketplace ..."
	claude plugin marketplace add "$(CURDIR)" --scope project
	@echo "Installing cc-senses-bridge from local marketplace ..."
	claude plugin install cc-senses-bridge@cc-senses-bridge --scope project
	@echo ""
	@echo "  ✓ plugin installed (project scope). Verify: make plugin_list"
	@echo "  Then: make run_cc  (try /speak /listen /see in the session)"

plugin_uninstall: ## Remove cc-senses-bridge plugin + local marketplace
	-claude plugin uninstall cc-senses-bridge
	-claude plugin marketplace remove cc-senses-bridge --scope project

plugin_list: ## Show installed Claude Code plugins
	claude plugin list

run_cc: ## Start Claude Code (run make plugin_install_local first)
	claude

run_voice: ## Start Claude Code with auto-read TTS (speaks every response after completion)
	CC_TTS_AUTO_READ=true claude

run_voice_stream: ## Start Claude Code with live streaming TTS (PTY proxy, may deadlock under bwrap)
	uv run cc-tts-wrap claude

run_voice_stream_json: ## Speak Claude response via stream-json (non-interactive, no PTY)
	@test -n "$(PROMPT)" || { echo "Usage: make run_voice_stream_json PROMPT='your question'"; exit 1; }
	uv run cc-tts-stream "$(PROMPT)"

run_repl: ## Interactive REPL with stream-json TTS (no Ink UI, sandbox-safe)
	uv run cc-tts-repl

reinstall_plugin: ## Force-reinstall cc-senses-bridge plugin (busts stale cache)
	claude plugin install cc-senses-bridge@cc-senses-bridge --force


# MARK: VERSION


bump_patch: ## Bump patch version (0.3.0 → 0.3.1)
	uv run bump-my-version bump patch

bump_minor: ## Bump minor version (0.3.0 → 0.4.0)
	uv run bump-my-version bump minor

bump_major: ## Bump major version (0.3.0 → 1.0.0)
	uv run bump-my-version bump major


# MARK: HELP


help: ## Show available recipes grouped by section
	@echo ""
	@echo "Usage: make [recipe]"
	@awk '/^# MARK:/ { \
		section = substr($$0, index($$0, ":")+2); \
		printf "\n\033[1m%s\033[0m\n", section \
	} \
	/^[a-zA-Z0-9_-]+:.*?##/ { \
		helpMessage = match($$0, /## (.*)/); \
		if (helpMessage) { \
			recipe = $$1; \
			sub(/:/, "", recipe); \
			printf "  \033[36m%-22s\033[0m %s\n", recipe, substr($$0, RSTART + 3, RLENGTH) \
		} \
	}' $(MAKEFILE_LIST)
	@echo ""
