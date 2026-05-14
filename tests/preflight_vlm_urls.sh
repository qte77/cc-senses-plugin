#!/usr/bin/env bash
# Pre-flight: verify every VLM model GGUF URL referenced by the Makefile
# returns HTTP 200. Run from an unsandboxed terminal — Claude Code's sandbox
# blocks huggingface.co.
#
# Usage:
#   bash tests/preflight_vlm_urls.sh
#   bash tests/preflight_vlm_urls.sh | tee /tmp/vlm_url_check.log
#
# Exit code: 0 if all URLs are 200, 1 otherwise.

set -uo pipefail

urls=(
  https://huggingface.co/moondream/moondream2-gguf/resolve/main/moondream2-text-model-f16.gguf
  https://huggingface.co/moondream/moondream2-gguf/resolve/main/moondream2-mmproj-f16.gguf
  https://huggingface.co/lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
  https://huggingface.co/lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-model-f16.gguf
  https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf
  https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf
  https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF/resolve/main/SmolVLM-500M-Instruct-Q8_0.gguf
  https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF/resolve/main/mmproj-SmolVLM-500M-Instruct-Q8_0.gguf
)

fail=0
for url in "${urls[@]}"; do
  code=$(curl -sIL -o /dev/null -w '%{http_code}' --max-time 30 "$url" || echo "ERR")
  printf '%s  %s\n' "$code" "$url"
  [[ "$code" == "200" ]] || fail=1
done

if [[ "$fail" -eq 0 ]]; then
  printf '\nAll 8 URLs returned 200.\n'
else
  printf '\nOne or more URLs failed. Re-check before locking into the Makefile.\n' >&2
fi

exit "$fail"
