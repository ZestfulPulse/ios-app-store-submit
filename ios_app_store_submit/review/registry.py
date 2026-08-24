"""Offline loader for the committed, normalized Apple rule registry.

This never fetches anything from developer.apple.com. It reads the
already-normalized snapshot committed at ``apple_rules/app_review_guidelines.json``
so tests and CLI runs work with no network access, and so the exact source
snapshot a Finding was generated against is always reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Ruleset

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "apple_rules" / "app_review_guidelines.json"


def load_ruleset(path: str | Path | None = None) -> Ruleset:
    target = Path(path).expanduser() if path is not None else DEFAULT_REGISTRY_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    return Ruleset.from_dict(data)
