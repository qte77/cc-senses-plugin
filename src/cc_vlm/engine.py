"""VLM engine abstraction and implementations.

Mirrors cc_stt.engine's Protocol + resolver pattern. MVP ships only
LlamaCppVLMEngine — in-process VLM via llama-cpp-python. No external
daemon. Model + mmproj files are loaded on first describe() call and
held for the lifetime of the Python process.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from cc_vlm import server_manager

if TYPE_CHECKING:
    from collections.abc import Callable


class VLMEngine(Protocol):
    """Protocol for vision-language model backends.

    describe() returns a text string suitable for injection into Claude's
    prompt context. Local VLMs return the actual image description; a
    future ClaudeVisionEngine would return a file path reference for
    Claude's built-in vision to pick up.
    """

    def describe(self, image_path: Path, prompt: str) -> str: ...

    def available(self) -> bool: ...

    @property
    def name(self) -> str: ...


# Map config handler_name → llama_cpp.llama_chat_format class name.
# Kept at module level so helper functions can consult it without
# accessing a "private" attribute on the engine class.
_HANDLER_MAP: dict[str, str] = {
    "qwen2.5vl": "Qwen25VLChatHandler",
    "llava15": "Llava15ChatHandler",
    "llava16": "Llava16ChatHandler",
    "moondream": "MoondreamChatHandler",
    "minicpmv": "MiniCPMv26ChatHandler",
    "nanollava": "NanollavaChatHandler",
}


class LlamaCppVLMEngine:
    """In-process VLM engine via llama-cpp-python.

    Loads a GGUF vision model plus its mmproj (CLIP projector) file on
    first describe() call and reuses the loaded model for subsequent
    calls within the same Python process. No external daemon; no HTTP.

    Cold start (fresh Python process + cold page cache): 3-5 s.
    Warm page cache (same session): 1-2 s.
    Within a single Python process after first call: 200-500 ms per
    describe() (the ⭐ latency cited in ai-agents-research #84).

    Default handler is Moondream2. For other model families set
    `handler_name` in config to one of:
      - "moondream" → MoondreamChatHandler  (default)
      - "qwen2.5vl" → Qwen25VLChatHandler
      - "llava15"/"llava16" → Llava15ChatHandler / Llava16ChatHandler
      - "minicpmv" → MiniCPMv26ChatHandler
      - "nanollava" → NanollavaChatHandler
    """

    def __init__(
        self,
        model_path: str = "",
        mmproj_path: str = "",
        handler_name: str = "moondream",
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        max_tokens: int = 256,
        **_kwargs: Any,
    ) -> None:
        # Reason: `_kwargs` absorbs server_url/server_model_alias etc. that
        # `resolve_vlm_engine` forwards uniformly to every engine in
        # `_ENGINE_TYPES`. They're meaningless for the in-process backend.
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.handler_name = handler_name
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.max_tokens = max_tokens
        self._llama: Any = None  # Lazily loaded llama_cpp.Llama instance.

    @property
    def name(self) -> str:
        return "llamacpp"

    def available(self) -> bool:
        """Check whether the engine can be used.

        Requires: (1) llama_cpp Python package installed,
        (2) model_path exists, (3) mmproj_path exists.
        Does NOT actually load the model — that happens lazily on
        describe() to keep available() cheap.
        """
        try:
            import llama_cpp  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return False
        if not self.model_path or not Path(self.model_path).exists():
            return False
        if not self.mmproj_path or not Path(self.mmproj_path).exists():
            return False
        if self.handler_name not in _HANDLER_MAP:
            return False
        return True

    def _load(self) -> Any:
        """Lazily load the Llama instance with chat handler on first call."""
        if self._llama is not None:
            return self._llama

        # Reason: these imports are intentionally runtime-lazy so that
        # `import cc_vlm` stays light and `available()` doesn't pay the
        # llama_cpp import cost (which touches native libraries).
        from llama_cpp import Llama  # type: ignore[import-not-found]
        from llama_cpp import llama_chat_format as lcf  # type: ignore[import-not-found]

        handler_cls_name = _HANDLER_MAP[self.handler_name]
        handler_cls: Callable[..., Any] = getattr(lcf, handler_cls_name)  # type: ignore[reportUnknownArgumentType]
        chat_handler = handler_cls(clip_model_path=self.mmproj_path)

        self._llama = Llama(
            model_path=self.model_path,
            chat_handler=chat_handler,
            n_ctx=self.n_ctx,
            n_gpu_layers=self.n_gpu_layers,
            verbose=False,
        )
        return self._llama

    def describe(self, image_path: Path, prompt: str) -> str:
        """Run the loaded VLM on (image, prompt) and return the text response.

        Loads the model on first call (lazy); subsequent calls reuse it
        within the same Python process.
        """
        llama = self._load()
        image_uri = f"file://{image_path.absolute()}"
        response = llama.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_uri}},
                    ],
                },
            ],
            max_tokens=self.max_tokens,
        )
        choices = response.get("choices", [])
        if not choices:
            msg = f"llama-cpp-python returned no choices: {response}"
            raise RuntimeError(msg)
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            msg = f"llama-cpp-python returned unexpected content shape: {message}"
            raise RuntimeError(msg)
        return content.strip()


class LlamaServerVLMEngine:
    """HTTP VLM engine that talks to `llama-server` over its OpenAI-compatible API.

    Routes around the `abetlen/llama-cpp-python` chat-handler gap (issue
    #102 for Qwen3-VL, no SmolVLMChatHandler upstream) by reaching the
    same `llama.cpp` binary via its HTTP server. The user starts the
    server themselves (Phase 1); we POST chat completions to it.

    The server keeps the model resident in RAM across `/see` invocations,
    so this path is *actually* warm — unlike the in-process engine,
    which reloads on every fresh Python process.
    """

    def __init__(
        self,
        server_url: str = "",
        server_model_alias: str = "",
        max_tokens: int = 256,
        auto_spawn: bool = False,
        model_path: str = "",
        mmproj_path: str = "",
        server_port: int = 8080,
        server_binary: str = "llama-server",
        **_kwargs: Any,
    ) -> None:
        # Reason: `_kwargs` absorbs handler_name/n_ctx/n_gpu_layers etc.
        # forwarded uniformly by `resolve_vlm_engine`. Those are meaningless
        # for the HTTP backend. model_path/mmproj_path/server_port/
        # server_binary are needed for Phase 2 lazy auto-spawn.
        self.server_url = server_url.rstrip("/")
        self.server_model_alias = server_model_alias
        self.max_tokens = max_tokens
        self.auto_spawn = auto_spawn
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.server_port = server_port
        self.server_binary = server_binary

    @property
    def name(self) -> str:
        return "llamaserver"

    def available(self) -> bool:
        """Check whether llama-server is reachable on `server_url`.

        Order:
          1. False if `server_url` empty.
          2. True if `GET /health` returns 200 (user-managed or already
             running). `server_manager.is_reachable` also returns False
             when `httpx` is not installed, so missing-deps is handled
             implicitly.
          3. False if `auto_spawn` is False, or url is non-localhost, or
             `model_path` / `mmproj_path` are unset.
          4. Otherwise call `server_manager.ensure_running` (Phase 2 lazy
             spawn). May take up to 30 s while the model loads.
        """
        if not self.server_url:
            return False
        if server_manager.is_reachable(self.server_url):
            return True
        if not self.auto_spawn:
            return False
        if not server_manager.is_localhost(self.server_url):
            return False
        if not self.model_path or not self.mmproj_path:
            return False
        return server_manager.ensure_running(
            self.server_url,
            self.server_port,
            self.server_binary,
            self.model_path,
            self.mmproj_path,
        )

    def describe(self, image_path: Path, prompt: str) -> str:
        """Read the image, POST a chat-completion to llama-server, return text.

        Image is base64-encoded into a data URL — llama-server's vision
        endpoints don't accept `file://` for security, and base64 is
        portable across all llama.cpp builds.
        """
        import base64

        import httpx

        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        data_url = f"data:{mime};base64,{image_b64}"

        body: dict[str, Any] = {
            "model": self.server_model_alias,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "max_tokens": self.max_tokens,
        }
        response = httpx.post(
            f"{self.server_url}/v1/chat/completions",
            json=body,
            timeout=60.0,
        )
        if response.status_code != 200:
            msg = f"llama-server returned {response.status_code}: {response.text}"
            raise RuntimeError(msg)
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            msg = f"llama-server returned no choices: {data}"
            raise RuntimeError(msg)
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            msg = f"llama-server returned unexpected content shape: {message}"
            raise RuntimeError(msg)
        return content.strip()


_VLMEngineType = type[LlamaCppVLMEngine] | type[LlamaServerVLMEngine]
_ENGINE_TYPES: list[_VLMEngineType] = [LlamaCppVLMEngine, LlamaServerVLMEngine]


def resolve_vlm_engine(
    engine_name: str = "auto",
    *,
    model_path: str = "",
    mmproj_path: str = "",
    handler_name: str = "moondream",
    n_ctx: int = 4096,
    n_gpu_layers: int = 0,
    max_tokens: int = 256,
    server_url: str = "",
    server_model_alias: str = "",
    auto_spawn: bool = False,
    server_port: int = 8080,
    server_binary: str = "llama-server",
) -> VLMEngine:
    """Resolve a VLM engine by name or auto-detect first available.

    Auto-detect order: LlamaCppVLMEngine (in-process) first, then
    LlamaServerVLMEngine (HTTP). The in-process backend wins when both
    are configured because it doesn't depend on an external daemon.
    """
    name_map: dict[str, _VLMEngineType] = {
        "llamacpp": LlamaCppVLMEngine,
        "llamaserver": LlamaServerVLMEngine,
    }

    kwargs: dict[str, Any] = {
        "model_path": model_path,
        "mmproj_path": mmproj_path,
        "handler_name": handler_name,
        "n_ctx": n_ctx,
        "n_gpu_layers": n_gpu_layers,
        "max_tokens": max_tokens,
        "server_url": server_url,
        "server_model_alias": server_model_alias,
        "auto_spawn": auto_spawn,
        "server_port": server_port,
        "server_binary": server_binary,
    }

    if engine_name != "auto":
        cls = name_map.get(engine_name)
        if cls is None:
            msg = f"Unknown engine: {engine_name}. Available: {', '.join(name_map)}"
            raise ValueError(msg)
        engine = cls(**kwargs)
        if not engine.available():
            msg = _unavailable_message(engine)
            raise RuntimeError(msg)
        return engine

    for cls in _ENGINE_TYPES:
        engine = cls(**kwargs)
        if engine.available():
            return engine

    msg = (
        "No VLM engine available. Run `make setup_see` for guided "
        "installation (downloads models, prints the matching "
        "llama-cpp-python install command for your hardware). Then set "
        "[vlm] model_path + mmproj_path in .cc-senses.toml or export "
        "CC_VLM_MODEL_PATH and CC_VLM_MMPROJ_PATH. Alternatively, run "
        "`llama-server` and set [vlm] server_url for the HTTP backend."
    )
    raise RuntimeError(msg)


def _unavailable_message(engine: LlamaCppVLMEngine | LlamaServerVLMEngine) -> str:
    """Diagnose why a specific engine is unavailable."""
    if isinstance(engine, LlamaServerVLMEngine):
        return _llamaserver_unavailable_message(engine)
    return _llamacpp_unavailable_message(engine)


def _llamaserver_unavailable_message(engine: LlamaServerVLMEngine) -> str:
    try:
        import httpx  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return (
            "httpx not installed. Install the [see] extras: "
            "`uv sync --extra see` — required for the llama-server backend."
        )
    if not engine.server_url:
        return (
            "No [vlm] server_url configured. Set in .cc-senses.toml or export "
            "CC_VLM_SERVER_URL (e.g. http://localhost:8080)."
        )
    return (
        f"llama-server unreachable at {engine.server_url}. "
        "Start it with `llama-server -m model.gguf --mmproj mmproj.gguf --port 8080`, "
        "or set [vlm] auto_spawn = true (Phase 2)."
    )


def _llamacpp_unavailable_message(engine: LlamaCppVLMEngine) -> str:
    try:
        import llama_cpp  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return (
            "llama-cpp-python not installed. Install the variant matching your "
            "hardware — see `make setup_see` output or skills/see/SKILL.md."
        )
    if not engine.model_path:
        return "No [vlm] model_path configured. Set in .cc-senses.toml or export CC_VLM_MODEL_PATH."
    if not Path(engine.model_path).exists():
        return f"VLM model file not found: {engine.model_path}"
    if not engine.mmproj_path:
        return (
            "No [vlm] mmproj_path configured. Set in .cc-senses.toml or export CC_VLM_MMPROJ_PATH."
        )
    if not Path(engine.mmproj_path).exists():
        return f"VLM mmproj file not found: {engine.mmproj_path}"
    if engine.handler_name not in _HANDLER_MAP:
        known = ", ".join(sorted(_HANDLER_MAP))
        return f"Unknown handler_name: {engine.handler_name!r}. Known: {known}"
    return "Engine unavailable for unknown reasons."
