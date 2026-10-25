"""Integration checks on the Makefile's setup targets.

1. Every setup_see* target must invoke `python -m cc_vlm.setup_models` with a
   key that exists in models.toml — catches a Make target added without its
   TOML stanza, or a renamed TOML key with a stale recipe.
2. Single-extra syncs must be `--inexact` — `uv sync` is exact by default, so a
   composite target (setup_all, setup_default_all) that chains `--extra piper`,
   `--extra stt`, `--extra see` would otherwise uninstall each earlier extra and
   the dev tools from setup_dev.

All other Makefile assertions (target exists, dry-run succeeds, .PHONY shape)
are either trivial smoke checks or are subsumed by the setup_models test suite.
"""

from __future__ import annotations

import re
from pathlib import Path

from cc_vlm.setup_models import load_models

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"

SETUP_MODELS_INVOCATION_RE = re.compile(r"python\s+-m\s+cc_vlm\.setup_models\s+(\S+)")


def test_every_setup_models_invocation_uses_a_known_key() -> None:
    keys_in_use = set(SETUP_MODELS_INVOCATION_RE.findall(MAKEFILE.read_text(encoding="utf-8")))
    known_keys = set(load_models())
    unknown = keys_in_use - known_keys
    assert not unknown, (
        f"Makefile invokes cc_vlm.setup_models with keys not present in models.toml: "
        f"{sorted(unknown)}. Known keys: {sorted(known_keys)}"
    )


EXTRA_SYNC_RE = re.compile(r"^\s*uv sync\b(?=.*--extra\b).*$", re.MULTILINE)


def test_single_extra_syncs_are_inexact() -> None:
    syncs = EXTRA_SYNC_RE.findall(MAKEFILE.read_text(encoding="utf-8"))
    assert syncs, "expected at least one `uv sync --extra` recipe line"
    exact = [line.strip() for line in syncs if "--inexact" not in line]
    assert not exact, (
        "`uv sync --extra X` is exact and uninstalls other extras when targets are "
        f"chained; add --inexact: {exact}"
    )
