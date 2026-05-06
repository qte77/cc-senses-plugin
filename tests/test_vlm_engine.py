"""Tests for cc_vlm.engine — VLMEngine Protocol + LlamaCppVLMEngine + resolver.

Mocks llama_cpp and llama_cpp.llama_chat_format via sys.modules so the test
suite runs without the llama-cpp-python package actually being installed.
This matches the shipped architecture (Python dep is intentionally outside
the [see] extras — users install the hardware-specific variant themselves).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cc_vlm.engine import LlamaCppVLMEngine, VLMEngine, resolve_vlm_engine


@pytest.fixture
def mock_llama_cpp() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Install fake llama_cpp / llama_chat_format modules into sys.modules.

    Returns: (fake_llama_cpp_module, fake_llama_chat_format_module,
              mock_llama_instance_that_describe_will_use)
    """
    fake_llama_module = MagicMock()
    fake_chat_format_module = MagicMock()

    # Create a default mock Llama instance for describe() calls
    mock_llama_instance = MagicMock()
    mock_llama_instance.create_chat_completion.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "A terminal window showing git status.",
                }
            }
        ]
    }
    fake_llama_module.Llama = MagicMock(return_value=mock_llama_instance)

    # Chat handler classes — each is itself a callable returning a mock
    fake_chat_format_module.Qwen25VLChatHandler = MagicMock(return_value=MagicMock())
    fake_chat_format_module.Llava15ChatHandler = MagicMock(return_value=MagicMock())
    fake_chat_format_module.MoondreamChatHandler = MagicMock(return_value=MagicMock())

    saved_llama = sys.modules.get("llama_cpp")
    saved_chat = sys.modules.get("llama_cpp.llama_chat_format")
    sys.modules["llama_cpp"] = fake_llama_module
    sys.modules["llama_cpp.llama_chat_format"] = fake_chat_format_module

    yield fake_llama_module, fake_chat_format_module, mock_llama_instance

    # Teardown: restore original sys.modules state
    if saved_llama is None:
        sys.modules.pop("llama_cpp", None)
    else:
        sys.modules["llama_cpp"] = saved_llama
    if saved_chat is None:
        sys.modules.pop("llama_cpp.llama_chat_format", None)
    else:
        sys.modules["llama_cpp.llama_chat_format"] = saved_chat


class TestVLMEngineProtocol:
    def test_protocol_shape(self, tmp_path: Path) -> None:
        """VLMEngine protocol requires describe, available, and name."""

        class FakeEngine:
            @property
            def name(self) -> str:
                return "fake"

            def available(self) -> bool:
                return True

            def describe(self, image_path: Path, prompt: str) -> str:
                return f"fake description of {image_path.name}"

        engine: VLMEngine = FakeEngine()
        img = tmp_path / "x.jpg"
        img.write_bytes(b"fake")
        assert engine.name == "fake"
        assert engine.available() is True
        assert engine.describe(img, "describe") == "fake description of x.jpg"


class TestLlamaCppVLMEngineDefaults:
    def test_name(self) -> None:
        assert LlamaCppVLMEngine().name == "llamacpp"

    def test_defaults(self) -> None:
        engine = LlamaCppVLMEngine()
        assert engine.model_path == ""
        assert engine.mmproj_path == ""
        assert engine.handler_name == "moondream"
        assert engine.n_ctx == 4096
        assert engine.n_gpu_layers == 0
        assert engine.max_tokens == 256
        assert engine._llama is None


class TestLlamaCppVLMEngineAvailable:
    def test_unavailable_when_llama_cpp_missing(self, tmp_path: Path) -> None:
        """Without llama_cpp installed, available() returns False."""
        # Ensure llama_cpp is NOT in sys.modules for this test
        saved = sys.modules.pop("llama_cpp", None)
        try:
            model = tmp_path / "m.gguf"
            mmproj = tmp_path / "mm.gguf"
            model.write_bytes(b"x")
            mmproj.write_bytes(b"x")
            engine = LlamaCppVLMEngine(model_path=str(model), mmproj_path=str(mmproj))
            assert engine.available() is False
        finally:
            if saved is not None:
                sys.modules["llama_cpp"] = saved

    def test_unavailable_when_model_path_empty(
        self, mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock]
    ) -> None:
        engine = LlamaCppVLMEngine(model_path="", mmproj_path="/tmp/mm.gguf")
        assert engine.available() is False

    def test_unavailable_when_model_path_missing(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        mmproj = tmp_path / "mm.gguf"
        mmproj.write_bytes(b"x")
        engine = LlamaCppVLMEngine(
            model_path=str(tmp_path / "nonexistent.gguf"),
            mmproj_path=str(mmproj),
        )
        assert engine.available() is False

    def test_unavailable_when_mmproj_path_missing(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        model.write_bytes(b"x")
        engine = LlamaCppVLMEngine(
            model_path=str(model),
            mmproj_path=str(tmp_path / "nonexistent.gguf"),
        )
        assert engine.available() is False

    def test_unavailable_when_handler_unknown(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = LlamaCppVLMEngine(
            model_path=str(model),
            mmproj_path=str(mmproj),
            handler_name="nonexistent-handler",
        )
        assert engine.available() is False

    def test_available_when_all_present(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = LlamaCppVLMEngine(model_path=str(model), mmproj_path=str(mmproj))
        assert engine.available() is True

    def test_available_with_moondream_handler(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = LlamaCppVLMEngine(
            model_path=str(model),
            mmproj_path=str(mmproj),
            handler_name="moondream",
        )
        assert engine.available() is True


class TestLlamaCppVLMEngineDescribe:
    @pytest.fixture
    def configured_engine(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> LlamaCppVLMEngine:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        return LlamaCppVLMEngine(model_path=str(model), mmproj_path=str(mmproj))

    def test_describe_returns_content(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        img = tmp_path / "screen.jpg"
        img.write_bytes(b"\xff\xd8fake")

        result = configured_engine.describe(img, "Describe the screen.")

        assert result == "A terminal window showing git status."

    def test_describe_loads_model_lazily_once(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        fake_module, _, _ = mock_llama_cpp
        img = tmp_path / "a.jpg"
        img.write_bytes(b"x")

        # First call triggers model load
        configured_engine.describe(img, "prompt 1")
        assert fake_module.Llama.call_count == 1

        # Second call reuses loaded model
        configured_engine.describe(img, "prompt 2")
        assert fake_module.Llama.call_count == 1  # unchanged

    def test_describe_passes_correct_llama_kwargs(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        fake_module, fake_cf, _ = mock_llama_cpp
        img = tmp_path / "a.jpg"
        img.write_bytes(b"x")

        configured_engine.describe(img, "prompt")

        # Llama() should receive model_path, chat_handler, n_ctx, n_gpu_layers, verbose=False
        call_kwargs = fake_module.Llama.call_args.kwargs
        assert call_kwargs["model_path"] == configured_engine.model_path
        assert call_kwargs["n_ctx"] == 4096
        assert call_kwargs["n_gpu_layers"] == 0
        assert call_kwargs["verbose"] is False
        assert "chat_handler" in call_kwargs

    def test_describe_messages_have_image_url(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        _, _, mock_instance = mock_llama_cpp
        img = tmp_path / "test.jpg"
        img.write_bytes(b"x")

        configured_engine.describe(img, "what is this")

        call_args = mock_instance.create_chat_completion.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        content = messages[0]["content"]
        # Multipart content: [text, image_url]
        assert any(
            item.get("type") == "text" and item.get("text") == "what is this" for item in content
        )
        image_items = [item for item in content if item.get("type") == "image_url"]
        assert len(image_items) == 1
        url = image_items[0]["image_url"]["url"]
        assert url.startswith("file://")
        assert str(img.absolute()) in url

    def test_describe_strips_whitespace(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        _, _, mock_instance = mock_llama_cpp
        mock_instance.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "  trimmed.  \n"}}]
        }
        img = tmp_path / "x.jpg"
        img.write_bytes(b"x")

        result = configured_engine.describe(img, "prompt")
        assert result == "trimmed."

    def test_describe_raises_on_no_choices(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        _, _, mock_instance = mock_llama_cpp
        mock_instance.create_chat_completion.return_value = {"choices": []}
        img = tmp_path / "x.jpg"
        img.write_bytes(b"x")

        with pytest.raises(RuntimeError, match="no choices"):
            configured_engine.describe(img, "prompt")

    def test_describe_raises_on_unexpected_content_shape(
        self,
        configured_engine: LlamaCppVLMEngine,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        _, _, mock_instance = mock_llama_cpp
        mock_instance.create_chat_completion.return_value = {
            "choices": [{"message": {"content": ["list", "not", "string"]}}]
        }
        img = tmp_path / "x.jpg"
        img.write_bytes(b"x")

        with pytest.raises(RuntimeError, match="unexpected content shape"):
            configured_engine.describe(img, "prompt")


class TestResolveVLMEngine:
    def test_auto_returns_llamacpp_when_available(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = resolve_vlm_engine("auto", model_path=str(model), mmproj_path=str(mmproj))
        assert isinstance(engine, LlamaCppVLMEngine)

    def test_auto_raises_when_nothing_available(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        with pytest.raises(RuntimeError, match="No VLM engine available"):
            resolve_vlm_engine("auto")

    def test_explicit_llamacpp_name(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = resolve_vlm_engine("llamacpp", model_path=str(model), mmproj_path=str(mmproj))
        assert isinstance(engine, LlamaCppVLMEngine)

    def test_auto_resolves_with_moondream_handler(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        tmp_path: Path,
    ) -> None:
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = resolve_vlm_engine(
            "auto",
            model_path=str(model),
            mmproj_path=str(mmproj),
            handler_name="moondream",
        )
        assert isinstance(engine, LlamaCppVLMEngine)
        assert engine.handler_name == "moondream"

    def test_unknown_engine_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown engine"):
            resolve_vlm_engine("nonexistent")

    def test_explicit_engine_not_available_raises_with_helpful_message(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        with pytest.raises(RuntimeError, match="model_path"):
            resolve_vlm_engine("llamacpp")

    def test_explicit_engine_raises_when_llama_cpp_not_installed(
        self,
    ) -> None:
        """Diagnostic message should point users at `make setup_see`."""
        saved = sys.modules.pop("llama_cpp", None)
        try:
            with pytest.raises(RuntimeError, match="llama-cpp-python not installed"):
                resolve_vlm_engine("llamacpp")
        finally:
            if saved is not None:
                sys.modules["llama_cpp"] = saved
