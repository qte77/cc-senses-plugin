"""VLM engine abstraction and implementations.

Mirrors cc_stt.engine's Protocol + resolver pattern. MVP ships only
LlamaCppVLMEngine — in-process VLM via llama-cpp-python. No external
daemon. Model + mmproj files are loaded on first describe() call and
held for the lifetime of the Python process.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

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
    ) -> None:
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


_ENGINE_TYPES: list[type[LlamaCppVLMEngine]] = [LlamaCppVLMEngine]


def resolve_vlm_engine(
    engine_name: str = "auto",
    *,
    model_path: str = "",
    mmproj_path: str = "",
    handler_name: str = "qwen2.5vl",
    n_ctx: int = 4096,
    n_gpu_layers: int = 0,
    max_tokens: int = 256,
) -> VLMEngine:
    """Resolve a VLM engine by name or auto-detect first available.

    Auto-detect order: LlamaCppVLMEngine (only MVP engine). Future:
    LlamaServerVLMEngine alternative, ClaudeVisionEngine fallback.
    """
    name_map: dict[str, type[LlamaCppVLMEngine]] = {
        "llamacpp": LlamaCppVLMEngine,
    }

    kwargs: dict[str, Any] = {
        "model_path": model_path,
        "mmproj_path": mmproj_path,
        "handler_name": handler_name,
        "n_ctx": n_ctx,
        "n_gpu_layers": n_gpu_layers,
        "max_tokens": max_tokens,
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
        "CC_VLM_MODEL_PATH and CC_VLM_MMPROJ_PATH."
    )
    raise RuntimeError(msg)


def _unavailable_message(engine: LlamaCppVLMEngine) -> str:
    """Diagnose why a specific engine is unavailable."""
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
