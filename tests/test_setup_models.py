"""Tests for cc_vlm.setup_models — TOML-driven model registry + CLI.

Each test targets a real bug class:
- Filename/URL drift (the bug that shipped the dead Makefile URLs)
- Engine/schema mismatch (llamacpp missing handler_name, etc.)
- Snippet leakage across engines (in-process target accidentally emits server_url)
- CLI error paths (unknown key, missing arg)

Trivial existence/data-echo tests are deliberately omitted.
"""

from __future__ import annotations

import io
import tomllib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from cc_vlm.setup_models import (
    MODELS_TOML,
    ModelSpec,
    format_snippet,
    load_models,
    main,
)

# --- Data-shape contract: filenames come from URLs, never hand-typed ---


class TestFilenameDerivation:
    """The original bug — Makefile hardcoded `f16_ct-q4_0.gguf` while the URL
    pointed at a different filename. After pivot, filename comes from URL basename
    by construction. This test makes the property hold for every shipped model."""

    @pytest.mark.parametrize("key", ["moondream", "qwen25vl", "qwen3vl", "smolvlm"])
    def test_filenames_match_url_basenames(self, key: str) -> None:
        spec = load_models()[key]
        assert spec.model_filename == spec.model_url.rsplit("/", 1)[-1]
        assert spec.mmproj_filename == spec.mmproj_url.rsplit("/", 1)[-1]


# --- Schema enforcement: engine-specific required keys ---


class TestSchemaValidation:
    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "models.toml"
        path.write_text(body)
        return path

    def test_llamacpp_missing_handler_name_raises(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            '[m]\ntitle="x"\nengine="llamacpp"\n'
            'model_url="https://h/a/b/resolve/main/m.gguf"\n'
            'mmproj_url="https://h/a/b/resolve/main/p.gguf"\n',
        )
        with pytest.raises(ValueError, match="handler_name"):
            load_models(path)

    def test_llamaserver_missing_server_url_raises(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            '[m]\ntitle="x"\nengine="llamaserver"\n'
            'model_url="https://h/a/b/resolve/main/m.gguf"\n'
            'mmproj_url="https://h/a/b/resolve/main/p.gguf"\n',
        )
        with pytest.raises(ValueError, match="server_url"):
            load_models(path)

    def test_unknown_engine_raises(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            '[m]\ntitle="x"\nengine="vllm"\n'
            'model_url="https://h/a/b/resolve/main/m.gguf"\n'
            'mmproj_url="https://h/a/b/resolve/main/p.gguf"\n',
        )
        with pytest.raises(ValueError, match="engine"):
            load_models(path)


# --- Snippet emission: each engine's [vlm] block has the right keys, no leakage ---


class TestSnippetEmission:
    def test_llamacpp_snippet_has_handler_name_and_no_server_url(self) -> None:
        spec = ModelSpec(
            key="m",
            title="M",
            engine="llamacpp",
            handler_name="moondream",
            model_url="https://h/a/b/resolve/main/m.gguf",
            mmproj_url="https://h/a/b/resolve/main/p.gguf",
        )
        out = format_snippet(spec, Path("/tmp/m.gguf"), Path("/tmp/p.gguf"))
        assert 'handler_name = "moondream"' in out
        assert "server_url" not in out
        assert 'engine = "llamaserver"' not in out

    def test_llamaserver_snippet_has_server_url_and_no_handler_name(self) -> None:
        spec = ModelSpec(
            key="m",
            title="M",
            engine="llamaserver",
            server_url="http://127.0.0.1:8080",
            model_url="https://h/a/b/resolve/main/m.gguf",
            mmproj_url="https://h/a/b/resolve/main/p.gguf",
        )
        out = format_snippet(spec, Path("/tmp/m.gguf"), Path("/tmp/p.gguf"))
        assert 'engine = "llamaserver"' in out
        assert 'server_url = "http://127.0.0.1:8080"' in out
        assert "handler_name" not in out

    def test_snippet_is_round_trip_parseable_as_toml(self) -> None:
        """The emitted snippet must be valid TOML the user can paste verbatim."""
        spec = load_models()["qwen3vl"]
        out = format_snippet(spec, Path("/tmp/m.gguf"), Path("/tmp/p.gguf"))
        # The snippet starts with [vlm], so tomllib will parse it as a section.
        parsed = tomllib.loads(out)
        assert parsed["vlm"]["engine"] == "llamaserver"
        assert parsed["vlm"]["server_url"] == "http://127.0.0.1:8080"


# --- CLI error paths ---


class TestMainCLI:
    def test_unknown_key_exits_nonzero_and_lists_available(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            rc = main(["does-not-exist"])
        assert rc != 0
        # User must be told what IS available
        assert "moondream" in stderr.getvalue()

    def test_wrong_argv_count_returns_nonzero(self) -> None:
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            assert main([]) != 0
            assert main(["a", "b"]) != 0


# --- The TOML file ships in the package ---


def test_models_toml_is_packaged() -> None:
    """Sanity: the data file must be importable from the installed package, not
    just present in the source tree. Catches missing hatch build inclusion."""
    assert MODELS_TOML.is_file(), f"models.toml not found at {MODELS_TOML}"
