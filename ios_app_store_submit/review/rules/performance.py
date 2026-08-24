"""Guideline 2.1-flavored performance/completeness rules.

Two rules bridge existing readiness technical findings (project structure,
version/build); two add new deterministic checks scoped to this phase
(a broad, non-blocking placeholder-text scan, and a narrow, blocking
dependency -> required-usage-description-key check).
"""

from __future__ import annotations

import re

from ...readiness.inspector import ProjectInspector, evidence_for_line
from ...readiness.models import Evidence, ReadinessReport, Status, aggregate_status
from ..models import Confidence, ReviewFinding, Ruleset
from ._bridge import bridge_readiness_finding

STRUCTURE_FINDING_IDS = ("technical.project", "technical.pubspec", "technical.info_plist")

PLACEHOLDER_TEXT = re.compile(r"\b(TODO|TBD|lorem ipsum|your name here)\b", re.IGNORECASE)
EXAMPLE_DOMAIN = re.compile(r"https?://(?:www\.)?example\.com", re.IGNORECASE)
DOC_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt"}

# Conservative, narrow mapping: a pubspec dependency known to need a specific
# Info.plist usage-description key. Deliberately small; extend only with
# well-known, unambiguous package -> permission relationships.
PERMISSION_DEPENDENCY_MAP: dict[str, tuple[str, ...]] = {
    "camera": ("NSCameraUsageDescription",),
    "image_picker": ("NSPhotoLibraryUsageDescription",),
    "photo_manager": ("NSPhotoLibraryUsageDescription",),
    "geolocator": ("NSLocationWhenInUseUsageDescription",),
    "location": ("NSLocationWhenInUseUsageDescription",),
    "speech_to_text": ("NSMicrophoneUsageDescription", "NSSpeechRecognitionUsageDescription"),
    "record": ("NSMicrophoneUsageDescription",),
    "flutter_contacts": ("NSContactsUsageDescription",),
}
DEPENDENCY_LINE = re.compile(r"^ {2}([A-Za-z_][A-Za-z0-9_]*)\s*:", re.MULTILINE)


def _finding_id(rule_id: str) -> str:
    return f"review.{rule_id.lower().replace('.', '_')}"


def _project_structure(readiness_report: ReadinessReport, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.PERFORMANCE.PROJECT_STRUCTURE")
    matches = [f for f in readiness_report.findings if f.finding_id in STRUCTURE_FINDING_IDS]
    status = aggregate_status(matches) if matches else Status.UNKNOWN
    worst = [f for f in matches if f.status is status] or matches
    evidence = tuple(item for f in worst for item in f.evidence)
    message = "; ".join(f.message for f in worst) or "Project structure could not be evaluated."
    return ReviewFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
        category=rule.category, status=status.value, confidence=Confidence.HIGH, message=message,
        evidence=evidence, source_url=rule.source_url, source_last_updated=rule.source_last_updated,
        ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
    )


def _version_build(readiness_report: ReadinessReport, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.PERFORMANCE.VERSION_BUILD")
    finding = next(f for f in readiness_report.findings if f.finding_id == "technical.pubspec_version")
    return bridge_readiness_finding(rule, finding, ruleset.ruleset_id)


def _placeholder_config(inspector: ProjectInspector, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.PERFORMANCE.PLACEHOLDER_CONFIG")
    matches: list[tuple] = []
    for path in inspector.all_text_files():
        if path.suffix.lower() not in DOC_SUFFIXES:
            continue
        relative = inspector.relative(path)
        text = inspector.read_text(relative)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if PLACEHOLDER_TEXT.search(line) or EXAMPLE_DOMAIN.search(line):
                matches.append((path, line_no, line.strip()))
    if matches:
        evidence = tuple(evidence_for_line(inspector, inspector.relative(p), ln, txt) for p, ln, txt in matches[:10])
        return ReviewFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
            category=rule.category, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(matches)} possible placeholder marker(s) in local docs/config; location is not proven review-facing.",
            evidence=evidence, source_url=rule.source_url, source_last_updated=rule.source_last_updated,
            ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
            suggested_fix="Review each match and replace placeholder text before submission.",
        )
    return ReviewFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
        category=rule.category, status="PASS", confidence=Confidence.MEDIUM,
        message="No placeholder markers were found in local docs/config.",
        evidence=(Evidence(kind="inspection", observed="not found", expected="placeholder marker", source="read-only inspection"),),
        source_url=rule.source_url, source_last_updated=rule.source_last_updated,
        ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
    )


def _detected_permission_dependencies(pubspec_text: str) -> dict[str, tuple[str, ...]]:
    names = set(DEPENDENCY_LINE.findall(pubspec_text))
    return {name: keys for name, keys in PERMISSION_DEPENDENCY_MAP.items() if name in names}


def _permission_descriptions(inspector: ProjectInspector, ruleset: Ruleset) -> ReviewFinding:
    rule = ruleset.rule("REVIEW.PERFORMANCE.PERMISSION_DESCRIPTIONS")
    pubspec = inspector.read_text("pubspec.yaml") or ""
    detected = _detected_permission_dependencies(pubspec)
    info_path = "ios/Runner/Info.plist"
    values = inspector.plist_values(info_path)
    missing = [(name, key) for name, keys in detected.items() for key in keys
               if not (isinstance(values.get(key), str) and values.get(key).strip())]
    if missing:
        evidence = tuple(
            Evidence(kind="plist", path=info_path, key=key, observed=values.get(key),
                      expected=f"non-empty {key}", source="project")
            for _name, key in missing
        ) + tuple(
            Evidence(kind="yaml", path="pubspec.yaml", key=name, observed="dependency present",
                      expected=f"matching usage-description key {key}", source="project")
            for name, key in missing
        )
        return ReviewFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
            category=rule.category, status="BLOCKED", confidence=Confidence.HIGH,
            message="Missing/empty usage-description key(s) for detected dependencies: "
                    + ", ".join(f"{name}->{key}" for name, key in missing),
            evidence=evidence, source_url=rule.source_url, source_last_updated=rule.source_last_updated,
            ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
            suggested_fix="Add the missing NS*UsageDescription key(s) with a real, specific rationale string.",
        )
    message = ("No known permission-requiring dependency is missing its usage-description key."
               if detected else "No known permission-requiring dependencies were detected in pubspec.yaml.")
    return ReviewFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, apple_guideline=rule.apple_guideline,
        category=rule.category, status="PASS", confidence=Confidence.HIGH, message=message,
        evidence=(Evidence(kind="yaml", path="pubspec.yaml", observed=sorted(detected) or "none",
                            expected="mapped usage-description keys present", source="project"),),
        source_url=rule.source_url, source_last_updated=rule.source_last_updated,
        ruleset_id=ruleset.ruleset_id, fixability=rule.fixability,
    )


def evaluate(inspector: ProjectInspector, readiness_report: ReadinessReport, ruleset: Ruleset) -> list[ReviewFinding]:
    return [
        _project_structure(readiness_report, ruleset),
        _version_build(readiness_report, ruleset),
        _placeholder_config(inspector, ruleset),
        _permission_descriptions(inspector, ruleset),
    ]
