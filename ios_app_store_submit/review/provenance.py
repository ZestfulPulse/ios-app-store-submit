"""Provenance/evidence enforcement for Phase 3 review findings.

Kept dependency-free of ``models.py`` (primitives in, exception out) so
``models.py`` can call this during construction without a circular import,
and tests can call it directly against raw field values.
"""

from __future__ import annotations

from typing import Any, Iterable

REQUIRED_PROVENANCE_FIELDS = ("rule_id", "apple_guideline", "source_url", "source_last_updated", "ruleset_id")


def validate_blocked_provenance(
    *,
    status: str,
    evidence: Iterable[Any],
    rule_id: str | None,
    apple_guideline: str | None,
    source_url: str | None,
    source_last_updated: str | None,
    ruleset_id: str | None,
) -> None:
    """Raise ValueError if a BLOCKED finding lacks evidence or rule provenance.

    A BLOCKED review finding is a claim that this specific Apple guideline is
    violated; without evidence and a citation back to the rule that produced
    it, that claim cannot be trusted or audited, so construction must fail.
    """
    if status != "BLOCKED":
        return
    missing: list[str] = []
    if not list(evidence):
        missing.append("evidence")
    values = {
        "rule_id": rule_id, "apple_guideline": apple_guideline, "source_url": source_url,
        "source_last_updated": source_last_updated, "ruleset_id": ruleset_id,
    }
    for field in REQUIRED_PROVENANCE_FIELDS:
        if not values[field]:
            missing.append(field)
    if missing:
        raise ValueError(f"BLOCKED review finding missing required evidence/provenance: {', '.join(missing)}")
