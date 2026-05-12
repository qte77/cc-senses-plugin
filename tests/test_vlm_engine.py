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

from cc_vlm.engine import (
    LlamaCppVLMEngine,
    LlamaServerVLMEngine,
    VLMEngine,
    resolve_vlm_engine,
)


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

    def test_auto_unavailable_message_points_at_setup_see(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        """Error message must reference `make setup_see`, not a hardcoded HF URL."""
        with pytest.raises(RuntimeError) as exc_info:
            resolve_vlm_engine("auto")
        message = str(exc_info.value)
        assert "make setup_see" in message
        assert "huggingface.co" not in message

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


@pytest.fixture
def mock_httpx() -> MagicMock:
    """Install a fake httpx module into sys.modules.

    Returns the fake httpx MagicMock. Tests configure `.get.return_value`
    and `.post.return_value` (or `.side_effect`) to drive engine behavior.
    `fake_httpx.ConnectError` and `.TimeoutException` are wired to real
    exception classes so engines can catch them by type.
    """
    fake = MagicMock()

    class FakeConnectError(Exception):
        pass

    class FakeTimeoutError(Exception):
        pass

    fake.ConnectError = FakeConnectError
    fake.TimeoutException = FakeTimeoutError

    default_response = MagicMock()
    default_response.status_code = 200
    default_response.text = "OK"
    default_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "A terminal showing git status."}}]
    }
    fake.get.return_value = default_response
    fake.post.return_value = default_response

    saved = sys.modules.get("httpx")
    sys.modules["httpx"] = fake
    yield fake
    if saved is None:
        sys.modules.pop("httpx", None)
    else:
        sys.modules["httpx"] = saved


class TestLlamaServerVLMEngineDefaults:
    def test_name(self) -> None:
        assert LlamaServerVLMEngine().name == "llamaserver"

    def test_defaults(self) -> None:
        engine = LlamaServerVLMEngine()
        assert engine.server_url == ""
        assert engine.server_model_alias == ""
        assert engine.max_tokens == 256

    def test_strips_trailing_slash_from_url(self) -> None:
        engine = LlamaServerVLMEngine(server_url="http://localhost:8080/")
        assert engine.server_url == "http://localhost:8080"

    def test_accepts_and_ignores_irrelevant_kwargs(self) -> None:
        """Forwarded kwargs from resolve_vlm_engine for the in-process engine
        must not break the HTTP engine's constructor."""
        engine = LlamaServerVLMEngine(
            server_url="http://localhost:8080",
            model_path="/ignored.gguf",
            mmproj_path="/ignored-mm.gguf",
            handler_name="moondream",
            n_ctx=4096,
            n_gpu_layers=0,
        )
        assert engine.server_url == "http://localhost:8080"


class TestLlamaServerVLMEngineAvailable:
    def test_unavailable_when_server_url_empty(self) -> None:
        engine = LlamaServerVLMEngine(server_url="")
        assert engine.available() is False

    def test_unavailable_when_httpx_missing(self) -> None:
        """Without httpx installed, available() returns False (no crash)."""
        saved = sys.modules.pop("httpx", None)
        sys.modules["httpx"] = None  # type: ignore[assignment]
        try:
            engine = LlamaServerVLMEngine(server_url="http://localhost:8080")
            assert engine.available() is False
        finally:
            sys.modules.pop("httpx", None)
            if saved is not None:
                sys.modules["httpx"] = saved

    def test_available_when_health_200(self, mock_httpx: MagicMock) -> None:
        engine = LlamaServerVLMEngine(server_url="http://localhost:8080")
        assert engine.available() is True
        mock_httpx.get.assert_called_once()
        called_url = mock_httpx.get.call_args.args[0]
        assert called_url == "http://localhost:8080/health"

    def test_unavailable_when_health_503(self, mock_httpx: MagicMock) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        engine = LlamaServerVLMEngine(server_url="http://localhost:8080")
        assert engine.available() is False

    def test_unavailable_on_connect_error(self, mock_httpx: MagicMock) -> None:
        mock_httpx.get.side_effect = mock_httpx.ConnectError("refused")
        engine = LlamaServerVLMEngine(server_url="http://localhost:8080")
        assert engine.available() is False

    def test_unavailable_on_timeout(self, mock_httpx: MagicMock) -> None:
        mock_httpx.get.side_effect = mock_httpx.TimeoutException("timeout")
        engine = LlamaServerVLMEngine(server_url="http://localhost:8080")
        assert engine.available() is False


class TestLlamaServerVLMEngineDescribe:
    @pytest.fixture
    def engine(self) -> LlamaServerVLMEngine:
        return LlamaServerVLMEngine(
            server_url="http://localhost:8080",
            server_model_alias="smolvlm2",
            max_tokens=128,
        )

    def test_describe_returns_stripped_content(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        mock_httpx.post.return_value.json.return_value = {
            "choices": [{"message": {"content": "  trimmed.  \n"}}]
        }
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8fake")

        result = engine.describe(img, "what is this")

        assert result == "trimmed."

    def test_describe_posts_to_chat_completions(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8fake")
        engine.describe(img, "prompt")

        called_url = mock_httpx.post.call_args.args[0]
        assert called_url == "http://localhost:8080/v1/chat/completions"

    def test_describe_body_has_model_and_base64_image(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8fake")
        engine.describe(img, "what is this")

        body = mock_httpx.post.call_args.kwargs["json"]
        assert body["model"] == "smolvlm2"
        assert body["max_tokens"] == 128
        content = body["messages"][0]["content"]
        text_items = [c for c in content if c.get("type") == "text"]
        image_items = [c for c in content if c.get("type") == "image_url"]
        assert text_items[0]["text"] == "what is this"
        url = image_items[0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        # The encoded payload should round-trip to the original bytes
        import base64

        b64 = url.split(",", 1)[1]
        assert base64.b64decode(b64) == b"\xff\xd8fake"

    def test_describe_detects_png_mime(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        img = tmp_path / "x.png"
        img.write_bytes(b"\x89PNGfake")
        engine.describe(img, "p")

        body = mock_httpx.post.call_args.kwargs["json"]
        url = body["messages"][0]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")

    def test_describe_raises_on_503(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        bad = MagicMock()
        bad.status_code = 503
        bad.text = "server overloaded"
        mock_httpx.post.return_value = bad
        img = tmp_path / "x.jpg"
        img.write_bytes(b"x")

        with pytest.raises(RuntimeError, match="503"):
            engine.describe(img, "p")

    def test_describe_raises_on_no_choices(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        mock_httpx.post.return_value.json.return_value = {"choices": []}
        img = tmp_path / "x.jpg"
        img.write_bytes(b"x")

        with pytest.raises(RuntimeError, match="no choices"):
            engine.describe(img, "p")

    def test_describe_raises_on_malformed_content(
        self, engine: LlamaServerVLMEngine, mock_httpx: MagicMock, tmp_path: Path
    ) -> None:
        mock_httpx.post.return_value.json.return_value = {
            "choices": [{"message": {"content": ["unexpected", "list"]}}]
        }
        img = tmp_path / "x.jpg"
        img.write_bytes(b"x")

        with pytest.raises(RuntimeError, match="unexpected content shape"):
            engine.describe(img, "p")


class TestResolveVLMEngineWithLlamaServer:
    def test_explicit_llamaserver_resolves(self, mock_httpx: MagicMock) -> None:
        engine = resolve_vlm_engine("llamaserver", server_url="http://localhost:8080")
        assert isinstance(engine, LlamaServerVLMEngine)

    def test_explicit_llamaserver_unavailable_raises(self, mock_httpx: MagicMock) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        with pytest.raises(RuntimeError, match="unreachable"):
            resolve_vlm_engine("llamaserver", server_url="http://localhost:8080")

    def test_auto_falls_back_to_llamaserver_when_only_server_set(
        self, mock_httpx: MagicMock
    ) -> None:
        """If model_path is empty but server_url is set and reachable, HTTP engine wins."""
        engine = resolve_vlm_engine("auto", server_url="http://localhost:8080")
        assert isinstance(engine, LlamaServerVLMEngine)

    def test_auto_prefers_llamacpp_when_both_configured(
        self,
        mock_llama_cpp: tuple[MagicMock, MagicMock, MagicMock],
        mock_httpx: MagicMock,
        tmp_path: Path,
    ) -> None:
        """In-process wins over HTTP when both are available (priority order)."""
        model = tmp_path / "m.gguf"
        mmproj = tmp_path / "mm.gguf"
        model.write_bytes(b"x")
        mmproj.write_bytes(b"x")
        engine = resolve_vlm_engine(
            "auto",
            model_path=str(model),
            mmproj_path=str(mmproj),
            server_url="http://localhost:8080",
        )
        assert isinstance(engine, LlamaCppVLMEngine)

    def test_unavailable_message_mentions_url(self, mock_httpx: MagicMock) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        with pytest.raises(RuntimeError) as exc_info:
            resolve_vlm_engine("llamaserver", server_url="http://localhost:9999")
        assert "http://localhost:9999" in str(exc_info.value)


class TestLlamaServerVLMEngineLazySpawn:
    """available() with auto_spawn=True should call server_manager.ensure_running
    when the initial /health probe fails. Engine doesn't import server_manager at
    module load; it's used inside available() — patch via the cc_vlm.engine
    module namespace."""

    def test_lazy_spawn_when_unreachable(
        self, mock_httpx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        spawn_calls = {"n": 0}

        def fake_ensure(*args: object, **kwargs: object) -> bool:
            spawn_calls["n"] += 1
            return True

        from cc_vlm import server_manager

        monkeypatch.setattr(server_manager, "ensure_running", fake_ensure)

        engine = LlamaServerVLMEngine(
            server_url="http://localhost:8080",
            auto_spawn=True,
            model_path="/m.gguf",
            mmproj_path="/mm.gguf",
            server_port=8080,
            server_binary="llama-server",
        )
        assert engine.available() is True
        assert spawn_calls["n"] == 1

    def test_no_spawn_when_auto_spawn_false(
        self, mock_httpx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        spawn_calls = {"n": 0}

        def fake_ensure(*args: object, **kwargs: object) -> bool:
            spawn_calls["n"] += 1
            return True

        from cc_vlm import server_manager

        monkeypatch.setattr(server_manager, "ensure_running", fake_ensure)

        engine = LlamaServerVLMEngine(
            server_url="http://localhost:8080",
            auto_spawn=False,
            model_path="/m.gguf",
            mmproj_path="/mm.gguf",
        )
        assert engine.available() is False
        assert spawn_calls["n"] == 0

    def test_no_spawn_when_non_localhost(
        self, mock_httpx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        spawn_calls = {"n": 0}

        def fake_ensure(*args: object, **kwargs: object) -> bool:
            spawn_calls["n"] += 1
            return True

        from cc_vlm import server_manager

        monkeypatch.setattr(server_manager, "ensure_running", fake_ensure)

        engine = LlamaServerVLMEngine(
            server_url="http://example.com:8080",
            auto_spawn=True,
            model_path="/m.gguf",
            mmproj_path="/mm.gguf",
        )
        assert engine.available() is False
        assert spawn_calls["n"] == 0

    def test_no_spawn_when_model_path_empty(
        self, mock_httpx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = MagicMock()
        bad.status_code = 503
        mock_httpx.get.return_value = bad
        spawn_calls = {"n": 0}

        def fake_ensure(*args: object, **kwargs: object) -> bool:
            spawn_calls["n"] += 1
            return True

        from cc_vlm import server_manager

        monkeypatch.setattr(server_manager, "ensure_running", fake_ensure)

        engine = LlamaServerVLMEngine(
            server_url="http://localhost:8080",
            auto_spawn=True,
            model_path="",
            mmproj_path="",
        )
        assert engine.available() is False
        assert spawn_calls["n"] == 0

    def test_resolver_forwards_auto_spawn(
        self, mock_httpx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit engine='llamaserver' should construct with the forwarded
        auto_spawn / server_port / server_binary kwargs."""
        engine = resolve_vlm_engine(
            "llamaserver",
            server_url="http://localhost:8080",
            auto_spawn=True,
            server_port=9090,
            server_binary="/usr/local/bin/llama-server",
        )
        assert isinstance(engine, LlamaServerVLMEngine)
        assert engine.auto_spawn is True
        assert engine.server_port == 9090
        assert engine.server_binary == "/usr/local/bin/llama-server"
