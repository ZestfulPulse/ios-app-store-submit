"""Guideline 5.1.1-flavored privacy-readiness bridge.

Does not automate App Privacy (nutrition label) publication in any way.
A usage-description key's presence is bridged as evidence of a *declared*
permission only -- it never implies the scope, purpose, or handling of
any associated data.
App Privacy publication status is always UNKNOWN unless an explicit local
attestation file is present; nothing here fabricates or infers it.
"""

from __future__ import annotations

import json

from ...readiness.inspector import ProjectInspector
from ...readiness.models import Evidence, ReadinessReport
from ..models import Confidence, ReviewFinding, Ruleset
from ._bridge import bridge_readiness_finding

APP_PRIVACY_MARKER_PATH = ".asc/app_privacy_published.json"


def _finding_id(rule_id: str) -> str:
    return f"review.{rule_id.lower().replace('.', '_')}"


def _permission_usage_descriptions(readiness_report: ReadinessReport, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.PRIVACY.PERMISSION_USAGE_DESCRIPTIONS")
    finding = next(f for f in readiness_report.findings if f.finding_id == "reviewability.permissions")
    return bridge_readiness_finding(
        rule, finding, ruleset.ruleset_id,
        message_override=finding.message + " (A declared usage-description key is evidence of a declared "
                          "permission only; it does not imply the scope, purpose, or handling of any "
                          "associated data.)",
    )


def _app_privacy_publication(inspector: ProjectInspector, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.PRIVACY.APP_PRIVACY_PUBLICATION")
    text = inspector.read_text(APP_PRIVACY_MARKER_PATH)
    if text is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data.get("declared") is True:
            return ReviewFinding(
                finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
                category=rule.category, status="PASS", confidence=Confidence.HIGH,
                message="Found an explicit local attestation that App Privacy details were published in App Store Connect.",
                evidence=(Evidence(kind="file", path=APP_PRIVACY_MARKER_PATH, observed=data,
                                    expected='{"declared": true, ...}', source="project"),),
                source_url=rule.source_url, source_last_updated=rule.source_last_updated,
                ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
            )
    return ReviewFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
        category=rule.category, status="UNKNOWN", confidence=Confidence.LOW,
        message="App Privacy publication status cannot be determined from a local project; App Store "
                "Connect state was not queried and no explicit local attestation file was found.",
        evidence=(Evidence(kind="inspection", path=APP_PRIVACY_MARKER_PATH, observed="not found",
                            expected="explicit local attestation", source="read-only inspection"),),
        source_url=rule.source_url, source_last_updated=rule.source_last_updated,
        ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
        requested_evidence=("Confirm in App Store Connect that App Privacy details have been published, "
                             "then optionally record that confirmation locally if this check should reflect it.",),
    )


def evaluate(inspector: ProjectInspector, readiness_report: ReadinessReport, ruleset: Ruleset) -> list[ReviewFinding]:
    return [
        _permission_usage_descriptions(readiness_report, ruleset),
        _app_privacy_publication(inspector, ruleset),
    ]
