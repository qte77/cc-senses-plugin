"""TOML-driven VLM model registry: download GGUFs and emit a `[vlm]` snippet.

Replaces the previous Makefile-string-template approach. URL/filename drift is
structurally impossible because filenames are derived from URL basenames.

Usage from a Make recipe:

    uv run python -m cc_vlm.setup_models <key>

Where <key> is a section header in `models.toml` (e.g. `moondream`, `qwen3vl`).
"""

from __future__ import annotations

import platform
import shutil
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODELS_TOML = Path(__file__).parent / "models.toml"
MODELS_DIR = Path.home() / ".cache" / "cc-senses-plugin" / "models"

_VALID_ENGINES = ("llamacpp", "llamaserver")
_LLAMA_CPP_INDEX_CPU = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
_LLAMA_CPP_INDEX_CUDA124 = "https://abetlen.github.io/llama-cpp-python/whl/cu124"


@dataclass(frozen=True)
class ModelSpec:
    key: str
    title: str
    engine: str
    model_url: str
    mmproj_url: str
    handler_name: str | None = None
    server_url: str | None = None

    @property
    def model_filename(self) -> str:
        return self.model_url.rsplit("/", 1)[-1]

    @property
    def mmproj_filename(self) -> str:
        return self.mmproj_url.rsplit("/", 1)[-1]


def load_models(path: Path | None = None) -> dict[str, ModelSpec]:
    source = path if path is not None else MODELS_TOML
    raw: dict[str, dict[str, Any]] = tomllib.loads(source.read_text(encoding="utf-8"))
    return {key: _build_spec(key, body) for key, body in raw.items()}


def _build_spec(key: str, body: dict[str, Any]) -> ModelSpec:
    engine = body.get("engine", "")
    if engine not in _VALID_ENGINES:
        raise ValueError(f"{key}: engine must be one of {_VALID_ENGINES}, got {engine!r}")
    if engine == "llamacpp" and "handler_name" not in body:
        raise ValueError(f"{key}: engine='llamacpp' requires handler_name")
    if engine == "llamaserver" and "server_url" not in body:
        raise ValueError(f"{key}: engine='llamaserver' requires server_url")
    return ModelSpec(
        key=key,
        title=body["title"],
        engine=engine,
        model_url=body["model_url"],
        mmproj_url=body["mmproj_url"],
        handler_name=body.get("handler_name"),
        server_url=body.get("server_url"),
    )


def download(url: str, dest: Path) -> bool:
    """Download `url` to `dest`. Returns True if downloaded, False if already present."""
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)
    return True


def format_snippet(spec: ModelSpec, model_path: Path, mmproj_path: Path) -> str:
    """Emit the `[vlm]` block the user pastes into `.cc-senses.toml`."""
    lines = ["[vlm]"]
    if spec.engine == "llamaserver":
        lines.append('engine = "llamaserver"')
        lines.append(f'server_url = "{spec.server_url}"')
    else:
        lines.append(f'handler_name = "{spec.handler_name}"')
    lines.append(f'model_path = "{model_path}"')
    lines.append(f'mmproj_path = "{mmproj_path}"')
    return "\n".join(lines)


def _print_install_hint(spec: ModelSpec) -> None:
    """Print the engine-specific runtime install instructions (not auto-installed)."""
    if spec.engine == "llamacpp":
        print("\n  Install llama-cpp-python for your hardware (NOT auto-installed):")
        if platform.system() == "Darwin":
            print(
                "    CMAKE_ARGS='-DLLAMA_METAL=on' uv pip install llama-cpp-python    # macOS Metal"
            )
        elif shutil.which("nvidia-smi"):
            print(
                f"    uv pip install llama-cpp-python --extra-index-url "
                f"{_LLAMA_CPP_INDEX_CUDA124}    # CUDA 12.4 detected"
            )
        else:
            print(
                f"    uv pip install llama-cpp-python --extra-index-url "
                f"{_LLAMA_CPP_INDEX_CPU}    # CPU"
            )
    else:
        print("\n  Requires llama-server on PATH (not auto-installed):")
        print("    Fedora/RHEL: sudo dnf install llama.cpp")
        print("    macOS:       brew install llama.cpp")
        print("    Other:       https://github.com/ggml-org/llama.cpp/releases")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python -m cc_vlm.setup_models <model-key>", file=sys.stderr)
        return 2
    key = args[0]
    models = load_models()
    if key not in models:
        print(f"Unknown model {key!r}. Available: {sorted(models)}", file=sys.stderr)
        return 1
    spec = models[key]
    model_path = MODELS_DIR / spec.model_filename
    mmproj_path = MODELS_DIR / spec.mmproj_filename
    for label, url, dest in (
        (f"{spec.title} model", spec.model_url, model_path),
        (f"{spec.title} mmproj", spec.mmproj_url, mmproj_path),
    ):
        if download(url, dest):
            print(f"Downloaded {label} -> {dest}")
        else:
            print(f"{label} already present - skipping.")
    _print_install_hint(spec)
    print("\n  Add this to .cc-senses.toml:\n")
    for line in format_snippet(spec, model_path, mmproj_path).splitlines():
        print(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
