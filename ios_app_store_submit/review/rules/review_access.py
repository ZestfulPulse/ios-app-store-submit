"""Guideline 2.1-flavored review-access rules.

All four rules bridge the existing readiness reviewability findings, which
already implement the conservative evidence policy this phase needs:
login detection is a heuristic and never BLOCKs by itself; the
demo/review-account finding only BLOCKs when login was detected *and* no
review-access evidence exists; backend detection is capped at ADVISORY
because a URL reference proves a dependency, not availability.
"""

from __future__ import annotations

from ...readiness.inspector import ProjectInspector
from ...readiness.models import ReadinessReport
from ..models import ReviewFinding, Ruleset
from ._bridge import bridge_readiness_finding


def _bridge(rule_id: str, source_finding_id: str, readiness_report: ReadinessReport, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule(rule_id)
    finding = next(f for f in readiness_report.findings if f.finding_id == source_finding_id)
    return bridge_readiness_finding(rule, finding, ruleset.ruleset_id)


def evaluate(inspector: ProjectInspector, readiness_report: ReadinessReport, ruleset: Ruleset) -> list[ReviewFinding]:
    return [
        _bridge("REVIEW.ACCESS.LOGIN_REQUIREMENT", "reviewability.login", readiness_report, ruleset),
        _bridge("REVIEW.ACCESS.DEMO_CREDENTIALS", "reviewability.review_info", readiness_report, ruleset),
        _bridge("REVIEW.ACCESS.REVIEW_NOTES", "reviewability.review_notes", readiness_report, ruleset),
        _bridge("REVIEW.ACCESS.BACKEND_DEPENDENCY", "reviewability.backend", readiness_report, ruleset),
    ]
