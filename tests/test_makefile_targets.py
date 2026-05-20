"""Integration check: every Makefile setup_see* target must invoke
`python -m cc_vlm.setup_models` with a key that exists in models.toml.

This is the only Makefile-level test worth keeping after the pivot — it catches
the failure mode where someone adds a Make target but forgets the TOML stanza,
or renames a TOML key but leaves the Make recipe stale.

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
