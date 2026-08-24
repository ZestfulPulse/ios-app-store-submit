"""Shared helper: turn an existing readiness Finding into a review ReviewFinding.

Every Phase 3 rule that reuses Phase 1/2 detection (rather than adding new
deterministic checks of its own) goes through here, so provenance is always
copied from the Rule object (the single source of truth in the registry),
never hand-typed per call site.
"""

from __future__ import annotations

from ...readiness.models import Finding
from ..models import ReviewFinding, Rule, confidence_from_float


def bridge_readiness_finding(
    rule: Rule, finding: Finding, ruleset_id: str, *,
    status_override: str | None = None,
    message_override: str | None = None,
    suggested_fix: str | None = None,
    requested_evidence: tuple[str, ...] = (),
) -> ReviewFinding:
    status = status_override or finding.status.value
    return ReviewFinding(
        finding_id=f"review.{rule.rule_id.lower().replace('.', '_')}",
        rule_id=rule.rule_id,
        apple_guideline=rule.apple_guideline,
        category=rule.category,
        status=status,
        confidence=confidence_from_float(finding.confidence),
        message=message_override or finding.message,
        evidence=finding.evidence,
        source_url=rule.source_url,
        source_last_updated=rule.source_last_updated,
        ruleset_id=ruleset_id,
        fixability=rule.fixability,
        suggested_fix=suggested_fix or finding.suggested_fix,
        requested_evidence=requested_evidence,
    )
