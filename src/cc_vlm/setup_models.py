"""TOML-driven VLM model registry: download GGUFs and emit a `[vlm]` snippet.

Replaces the previous Makefile-string-template approach. URL/filename drift is
structurally impossible because filenames are derived from URL basenames.

Usage from a Make recipe:

    uv run python -m cc_vlm.setup_models <key> [--install-runtime|-i] [--write-config|-w]

Where <key> is a section header in `models.toml` (e.g. `moondream`, `qwen3vl`).
Without flags it only prints the runtime install hint and the `[vlm]` snippet;
`-i` installs llama-cpp-python (or checks llama-server), `-w` upserts the
snippet into `./.cc-senses.toml` without overwriting a different `[vlm]`.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cc_voice_common.config import CONFIG_FILENAMES

CONFIG_FILENAME = CONFIG_FILENAMES[0]
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


def _llama_cpp_install() -> tuple[list[str], dict[str, str], str]:
    """Platform-detected (argv, extra env, label) for installing llama-cpp-python.

    `CC_VLM_LLAMA_CPP_INDEX` overrides the detected wheel index.
    """
    argv = ["uv", "pip", "install", "llama-cpp-python"]
    override = os.environ.get("CC_VLM_LLAMA_CPP_INDEX")
    if override:
        return [*argv, "--extra-index-url", override], {}, "CC_VLM_LLAMA_CPP_INDEX"
    if platform.system() == "Darwin":
        return argv, {"CMAKE_ARGS": "-DLLAMA_METAL=on"}, "macOS Metal"
    if shutil.which("nvidia-smi"):
        return [*argv, "--extra-index-url", _LLAMA_CPP_INDEX_CUDA124], {}, "CUDA 12.4 detected"
    return [*argv, "--extra-index-url", _LLAMA_CPP_INDEX_CPU], {}, "CPU"


def _print_install_hint(spec: ModelSpec) -> None:
    """Print the engine-specific runtime install instructions (not auto-installed)."""
    if spec.engine == "llamacpp":
        argv, env, label = _llama_cpp_install()
        prefix = "".join(f"{k}='{v}' " for k, v in env.items())
        print("\n  Install llama-cpp-python for your hardware (NOT auto-installed):")
        print(f"    {prefix}{' '.join(argv)}    # {label}")
    else:
        print("\n  Requires llama-server on PATH (not auto-installed):")
        print("    Fedora/RHEL: sudo dnf install llama.cpp")
        print("    macOS:       brew install llama.cpp")
        print("    Other:       https://github.com/ggml-org/llama.cpp/releases")


def _llama_cpp_installed() -> bool:
    return importlib.util.find_spec("llama_cpp") is not None


def install_runtime(spec: ModelSpec) -> bool:
    """Install (llamacpp) or check (llamaserver) the engine runtime. True when ready."""
    if spec.engine == "llamaserver":
        if shutil.which("llama-server"):
            return True
        _print_install_hint(spec)
        return False
    if _llama_cpp_installed():
        print("llama-cpp-python already installed - skipping.")
        return True
    argv, env, label = _llama_cpp_install()
    print(f"Installing llama-cpp-python ({label}) ...")
    try:
        subprocess.run(argv, check=True, env={**os.environ, **env})  # noqa: S603
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"llama-cpp-python install failed: {exc}")
        _print_install_hint(spec)
        return False
    return True


def upsert_vlm_config(snippet: str, config_path: Path) -> str:
    """Add the `[vlm]` snippet to config_path without clobbering user config.

    Returns "created", "appended", "unchanged", or "proposed" (an existing,
    different `[vlm]` is kept; the snippet goes to `<config>.proposed`).
    """
    if not config_path.exists():
        config_path.write_text(snippet + "\n", encoding="utf-8")
        return "created"
    text = config_path.read_text(encoding="utf-8")
    wanted = tomllib.loads(snippet)["vlm"]
    try:
        current = tomllib.loads(text).get("vlm")
    except tomllib.TOMLDecodeError:
        current = {}  # unparseable: never rewrite it, propose instead
    if current is None:
        separator = "" if text.endswith("\n") or not text else "\n"
        config_path.write_text(f"{text}{separator}\n{snippet}\n", encoding="utf-8")
        return "appended"
    if current == wanted:
        return "unchanged"
    proposed = config_path.with_name(config_path.name + ".proposed")
    proposed.write_text(snippet + "\n", encoding="utf-8")
    return "proposed"


_FLAGS = {"-i": "install", "--install-runtime": "install", "-w": "write", "--write-config": "write"}
_USAGE = (
    "Usage: python -m cc_vlm.setup_models <model-key> [--install-runtime|-i] [--write-config|-w]"
)


def _parse_args(args: list[str]) -> tuple[str, set[str]] | None:
    keys = [a for a in args if not a.startswith("-")]
    unknown = [a for a in args if a.startswith("-") and a not in _FLAGS]
    if len(keys) != 1 or unknown:
        return None
    return keys[0], {_FLAGS[a] for a in args if a in _FLAGS}


def _write_config(snippet: str) -> bool:
    config_path = Path.cwd() / CONFIG_FILENAME
    state = upsert_vlm_config(snippet, config_path)
    if state == "proposed":
        print(f"{config_path} already has a different [vlm]; left it unchanged.")
        print(f"  Merge {config_path}.proposed into it by hand.")
        return False
    print(f"{config_path}: [vlm] {state}.")
    return True


def main(argv: list[str] | None = None) -> int:
    parsed = _parse_args(sys.argv[1:] if argv is None else argv)
    if parsed is None:
        print(_USAGE, file=sys.stderr)
        return 2
    key, flags = parsed
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
    snippet = format_snippet(spec, model_path, mmproj_path)
    ok = True
    if "install" in flags:
        ok = install_runtime(spec) and ok
    else:
        _print_install_hint(spec)
    if "write" in flags:
        ok = _write_config(snippet) and ok
    else:
        print(f"\n  Add this to {CONFIG_FILENAME}:\n")
        for line in snippet.splitlines():
            print(f"    {line}")
    if flags:
        print("\n✓ /see runtime + config ready." if ok else "\n✗ /see setup incomplete, see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
