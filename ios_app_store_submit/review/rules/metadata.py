"""Guideline 2.3/5.1.1-flavored metadata completeness rules.

Most rules here bridge existing readiness metadata findings. The one new
check (placeholder content) is scoped to the *exact* review-facing fields
(display name, pubspec description) so a match is proof, not a guess, and
may legitimately BLOCK.
"""

from __future__ import annotations

import re

from ...readiness.inspector import ProjectInspector
from ...readiness.models import Evidence, ReadinessReport
from ..models import Confidence, ReviewFinding, Ruleset
from ._bridge import bridge_readiness_finding
from .performance import EXAMPLE_DOMAIN, PLACEHOLDER_TEXT


def _finding_id(rule_id: str) -> str:
    return f"review.{rule_id.lower().replace('.', '_')}"


def _bridge(rule_id: str, source_finding_id: str, readiness_report: ReadinessReport, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule(rule_id)
    finding = next(f for f in readiness_report.findings if f.finding_id == source_finding_id)
    return bridge_readiness_finding(rule, finding, ruleset.ruleset_id)


DESCRIPTION_LINE = re.compile(r"^description\s*:\s*(.+)$", re.MULTILINE)


def _placeholder_strings(inspector: ProjectInspector, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.METADATA.PLACEHOLDER_STRINGS")
    info_path = "ios/Runner/Info.plist"
    values = inspector.plist_values(info_path)
    display = values.get("CFBundleDisplayName") or values.get("CFBundleName")
    pubspec_text = inspector.read_text("pubspec.yaml") or ""
    desc_match = DESCRIPTION_LINE.search(pubspec_text)
    description = desc_match.group(1).strip() if desc_match else None

    hits: list[tuple[str, str]] = []
    if isinstance(display, str) and (PLACEHOLDER_TEXT.search(display) or EXAMPLE_DOMAIN.search(display)):
        hits.append((f"{info_path}:CFBundleDisplayName", display))
    if description and (PLACEHOLDER_TEXT.search(description) or EXAMPLE_DOMAIN.search(description)):
        hits.append(("pubspec.yaml:description", description))

    if hits:
        evidence = tuple(
            Evidence(kind="exact_field", path=path, observed=value,
                      expected="non-placeholder review-facing text", source="project")
            for path, value in hits
        )
        return ReviewFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
            category=rule.category, status="BLOCKED", confidence=Confidence.HIGH,
            message="Placeholder content found in an exact review-facing field: " + ", ".join(p for p, _ in hits),
            evidence=evidence, source_url=rule.source_url, source_last_updated=rule.source_last_updated,
            ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
            suggested_fix="Replace the placeholder text with real, review-facing content.",
        )
    return ReviewFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
        category=rule.category, status="PASS", confidence=Confidence.HIGH,
        message="No placeholder content was found in the exact review-facing fields checked.",
        evidence=(Evidence(kind="inspection", observed="not found", expected="placeholder text", source="read-only inspection"),),
        source_url=rule.source_url, source_last_updated=rule.source_last_updated,
        ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
    )


def evaluate(inspector: ProjectInspector, readiness_report: ReadinessReport, ruleset: Ruleset) -> list[ReviewFinding]:
    return [
        _bridge("REVIEW.METADATA.DISPLAY_NAME", "metadata.display_name", readiness_report, ruleset),
        _bridge("REVIEW.METADATA.VERSION_COHERENT", "technical.pubspec_version", readiness_report, ruleset),
        _bridge("REVIEW.METADATA.PRIVACY_URL_CANDIDATE", "metadata.privacy_policy", readiness_report, ruleset),
        _bridge("REVIEW.METADATA.SUPPORT_URL_CANDIDATE", "metadata.support_url", readiness_report, ruleset),
        _placeholder_strings(inspector, ruleset),
        _bridge("REVIEW.METADATA.LOCALIZATION_CONSISTENCY", "metadata.localizations", readiness_report, ruleset),
    ]
