"""Read-only project inspection helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


class ProjectInspector:
    """Small, dependency-free facade around a project directory."""

    def __init__(self, project_path: str | Path):
        self.root = Path(project_path).expanduser().resolve()

    def path(self, relative: str | Path) -> Path:
        return self.root / relative

    def exists(self, relative: str | Path) -> bool:
        return self.path(relative).exists()

    def files(self, patterns: Iterable[str]) -> list[Path]:
        found: set[Path] = set()
        for pattern in patterns:
            found.update(item for item in self.root.glob(pattern) if item.is_file())
        return sorted(found)

    def read_text(self, relative: str | Path) -> str | None:
        candidate = self.path(relative)
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def all_text_files(self) -> list[Path]:
        ignored = {".git", ".dart_tool", "build", ".asc"}
        # Phase 6's rejection-recovery input conventionally sits inside the
        # project directory being scanned (see recovery/report.py). It quotes
        # Apple's own rejection wording verbatim, which can otherwise trip
        # the very documentation heuristics (e.g. "demo account credentials")
        # this scan looks for -- so it is never treated as project evidence.
        ignored_names = {"rejection.txt", "rejection.json"}
        result = []
        for item in self.root.rglob("*"):
            if (not item.is_file() or item.name in ignored_names
                    or any(part in ignored for part in item.relative_to(self.root).parts)):
                continue
            try:
                item.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            result.append(item)
        return sorted(result)

    def search(self, pattern: str, files: Iterable[Path] | None = None) -> list[tuple[Path, int, str]]:
        expression = re.compile(pattern, re.IGNORECASE)
        matches: list[tuple[Path, int, str]] = []
        for path in files or self.all_text_files():
            text = self.read_text(self.relative(path))
            if text is None:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if expression.search(line):
                    matches.append((path, line_number, line.strip()))
        return matches

    def line_value(self, relative: str | Path, key: str) -> tuple[str, int] | None:
        text = self.read_text(relative)
        if text is None:
            return None
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^;]+))\s*;", re.MULTILINE)
        match = pattern.search(text)
        if not match:
            return None
        value = next((group for group in match.groups() if group is not None), "").strip()
        return value, text[:match.start()].count("\n") + 1

    def plist_values(self, relative: str | Path) -> dict[str, object]:
        import plistlib
        from xml.parsers.expat import ExpatError

        path = self.path(relative)
        try:
            with path.open("rb") as handle:
                value = plistlib.load(handle)
        except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
            return {}
        return value if isinstance(value, dict) else {}


def evidence_for_line(inspector: ProjectInspector, path: str, line: int, observed: str, *, key: str | None = None):
    from .models import Evidence

    return Evidence(
        kind="text",
        path=path,
        key=key,
        observed=observed,
        source="project",
        line=line,
    )
