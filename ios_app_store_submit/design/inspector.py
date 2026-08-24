"""Shared, read-only source-scanning helpers for the four Phase 5 area modules.

Framework coverage is intentionally narrow (Flutter/Dart first, a little
native iOS) and text/regex based. This is conservative source-code
approximation, never full static analysis or a parser with complete
language coverage -- callers must treat "no match" as "not established",
never as "proven absent."
"""

from __future__ import annotations

import re
from pathlib import Path

from ..readiness.inspector import ProjectInspector

CODE_SUFFIXES = {".dart", ".swift"}


def code_files(inspector: ProjectInspector) -> list[Path]:
    return [path for path in inspector.all_text_files() if path.suffix.lower() in CODE_SUFFIXES]


def _matching_paren(text: str, open_index: int) -> int | None:
    """Return the index just past the paren matching text[open_index] == '('."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def find_widget_invocations(inspector: ProjectInspector, widget_name: str, files: list[Path] | None = None):
    """Find every ``widget_name(...)`` call, returning (path, line, block_text, start_index, text).

    ``block_text`` is the balanced-paren text of the call, so a caller can
    look for named arguments (``width:``, ``tooltip:``, ...) even when the
    call spans multiple lines. A call whose parens never balance within the
    file (or that never closes) is skipped rather than guessed at.
    ``start_index``/``text`` let a caller look at a bounded window of the
    surrounding file text (e.g. to check for a wrapping ``Semantics(``)
    without re-reading the file.
    """
    pattern = re.compile(rf"\b{re.escape(widget_name)}\s*\(")
    results = []
    for path in files if files is not None else code_files(inspector):
        text = inspector.read_text(inspector.relative(path))
        if text is None:
            continue
        for match in pattern.finditer(text):
            open_index = match.end() - 1
            end_index = _matching_paren(text, open_index)
            if end_index is None:
                continue
            block = text[match.start():end_index]
            line = text[:match.start()].count("\n") + 1
            results.append((path, line, block, match.start(), text))
    return results


def extract_named_number(block_text: str, name: str) -> float | None:
    match = re.search(rf"\b{re.escape(name)}\s*:\s*(-?\d+(?:\.\d+)?)", block_text)
    if not match:
        return None
    return float(match.group(1))


def extract_named_string(block_text: str, name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}\s*:\s*['\"]([^'\"]*)['\"]", block_text)
    return match.group(1) if match else None


def has_named_arg(block_text: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\s*:", block_text) is not None


def load_localization_resource(inspector: ProjectInspector, relative_path: str) -> dict | None:
    import json

    text = inspector.read_text(relative_path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
