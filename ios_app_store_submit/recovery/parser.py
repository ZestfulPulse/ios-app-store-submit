"""Conservative rejection-text parsing.

Everything extracted here is a text-match signal, never an inference about
what actually happened. An explicit guideline number is only ever recorded
when the text literally contains one; nothing is invented when absent.
Local text/JSON input only -- Phase 6 never fetches App Store Connect.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import RejectionMessage, RejectionSource

_SECRET_VALUE_PATTERNS = tuple(
    re.compile(rf"\b({label})\s*[:=]\s*(\S+)", re.IGNORECASE)
    for label in ("password", "passwd", "pwd", "api[_-]?key", "api[_-]?secret", "token", "secret", "username")
)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def redact_secrets(text: str) -> str:
    """Mask secret-like values (passwords, API keys/tokens, usernames, emails).

    Used whenever rejection text is persisted into a report or surfaced in
    a human summary/reply draft. Never applied to the in-memory
    ``RejectionMessage.raw_text`` used for internal signal matching --
    only to derived/serialized output, per the Phase 6 security boundary.
    """
    redacted = text
    for pattern in _SECRET_VALUE_PATTERNS:
        redacted = pattern.sub(lambda m: f"{m.group(1)}: [REDACTED]", redacted)
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    return redacted


def redacted_rejection_dict(rejection: RejectionMessage) -> dict:
    """A JSON-safe dict for ``rejection`` with secret-like values masked."""
    data = rejection.to_dict()
    data["raw_text"] = redact_secrets(data["raw_text"])
    action = data.get("metadata", {}).get("action_requested")
    if action:
        data["metadata"]["action_requested"] = redact_secrets(action)
    return data

_GUIDELINE_PATTERN = re.compile(r"\bguideline\s+(\d+(?:\.\d+){0,2})", re.IGNORECASE)
_ATTACHMENT_PATTERN = re.compile(r"\b[\w\-]+\.(?:png|jpg|jpeg|mp4|mov|heic)\b", re.IGNORECASE)

# Apple's own rejection emails title each cited guideline as
# "Guideline X.Y - <Section> - <Sub-section>" (e.g. "Guideline 2.3 -
# Performance - Accurate Metadata", "Guideline 5.1.1 - Legal - Privacy -
# Data Collection and Storage"). Those section-name words (Performance,
# Legal, ...) are Apple's taxonomy labels, not a content signal about what
# actually went wrong -- so the header line is stripped before keyword
# scanning, to avoid mistaking Apple's own formatting for a crash/legal
# complaint. The guideline *number* is still extracted from the full text.
_GUIDELINE_HEADER_LINE = re.compile(r"^[ \t]*guideline\s+\d+(?:\.\d+){0,2}\s*-.*$", re.IGNORECASE | re.MULTILINE)

SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "device_platform": ("iphone", "ipad", "ipados", "ios 1", "ios 2", "apple watch", "apple tv"),
    "review_access": (
        "demo account", "review account", "credentials", "username", "password",
        "unable to sign in", "could not sign in", "log in", "login",
    ),
    "privacy": (
        "privacy", "data collection", "app privacy", "personal information", "permission",
        "tracking", "nutrition label",
    ),
    "metadata_refs": ("app description", "app name", "placeholder", "metadata", "keyword"),
    "crash_performance": ("crash", "crashed", "hang", "hung", "freeze", "froze", "unresponsive"),
    "design_hig": (
        "human interface guidelines", "touch target", "layout", "accessibility",
        "font size", "navigation", "safe area",
    ),
    "localization": (
        "localiz", "localis", "translat", "language support", "missing language",
    ),
    "screenshot": ("screenshot",),
    "payments_iap": ("in-app purchase", "in app purchase", "iap", "subscription", "payment"),
    "legal_policy": ("terms of use", "eula", "copyright", "trademark", "policy violation", "intellectual property"),
}

_ACTION_PATTERN = re.compile(r"([^.\n]*\bplease\b[^.\n]*\.)", re.IGNORECASE)
_REVIEW_STATE_PATTERNS = (
    (re.compile(r"\bmetadata rejected\b", re.IGNORECASE), "METADATA_REJECTED"),
    (re.compile(r"\bbinary rejected\b", re.IGNORECASE), "BINARY_REJECTED"),
    (re.compile(r"\bdeveloper rejected\b", re.IGNORECASE), "DEVELOPER_REJECTED"),
    (re.compile(r"\brejected\b", re.IGNORECASE), "REJECTED"),
)


def _extract_guideline_refs(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for match in _GUIDELINE_PATTERN.finditer(text):
        value = match.group(1)
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def _extract_signals(text: str) -> dict[str, list[str]]:
    lowered = _GUIDELINE_HEADER_LINE.sub("", text).lower()
    signals: dict[str, list[str]] = {}
    for category, keywords in SIGNAL_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in lowered]
        if hits:
            signals[category] = hits
    return signals


def _extract_review_state(text: str) -> str:
    for pattern, label in _REVIEW_STATE_PATTERNS:
        if pattern.search(text):
            return label
    return "REJECTED"


def _extract_action_requested(text: str) -> str | None:
    match = _ACTION_PATTERN.search(text)
    return match.group(1).strip() if match else None


def parse_rejection(
    raw_text: str, *, rejection_id: str, source: str | RejectionSource = RejectionSource.MANUAL_TEXT,
    received_at: str = "", extra_metadata: dict[str, Any] | None = None,
) -> RejectionMessage:
    guideline_refs = _extract_guideline_refs(raw_text)
    signals = _extract_signals(raw_text)
    action_requested = _extract_action_requested(raw_text)
    attachments = tuple(dict.fromkeys(match.group(0) for match in _ATTACHMENT_PATTERN.finditer(raw_text)))
    review_state = _extract_review_state(raw_text)

    metadata: dict[str, Any] = {"signals": signals}
    if action_requested:
        metadata["action_requested"] = action_requested
    if extra_metadata:
        metadata.update(extra_metadata)

    return RejectionMessage(
        rejection_id=rejection_id, source=source, received_at=received_at, raw_text=raw_text,
        guideline_refs=guideline_refs, review_state=review_state, attachments=attachments, metadata=metadata,
    )


def parse_rejection_file(
    path: str | Path, *, rejection_id: str | None = None, source: str | RejectionSource | None = None,
) -> RejectionMessage:
    """Load a rejection from a local .txt or .json file. Never fetches ASC."""
    target = Path(path).expanduser()
    text = target.read_text(encoding="utf-8")
    default_id = rejection_id or target.stem

    if target.suffix.lower() == ".json":
        data = json.loads(text)
        raw_text = data.get("raw_text", "")
        return parse_rejection(
            raw_text, rejection_id=data.get("rejection_id", default_id),
            source=source or data.get("source", RejectionSource.ASC_EXPORT),
            received_at=data.get("received_at", ""), extra_metadata=data.get("metadata"),
        )

    return parse_rejection(text, rejection_id=default_id, source=source or RejectionSource.MANUAL_TEXT)
