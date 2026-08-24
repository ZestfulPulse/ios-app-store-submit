"""Parse and validate local PrivacyInfo.xcprivacy manifest files.

App Store Connect may reject invalid privacy manifest files, so structural
validation is deterministic and may surface a HIGH-severity issue. This
module never auto-repairs manifest *semantics* (data types, tracking
flags, domains, purposes) -- only Phase 2's existing safe, non-semantic
formatting-repair boundary may ever touch these files, and this module does
not call into that boundary at all; it only reads.
"""

from __future__ import annotations

import json
import plistlib
from pathlib import Path
from xml.parsers.expat import ExpatError

from ..readiness.inspector import ProjectInspector
from .models import Confidence, PrivacyEvidence, Purpose, Severity, TriState, tri_state

_DATA_TYPE_CATALOG_PATH = Path(__file__).resolve().parents[2] / "apple_rules" / "app_privacy_data_types.json"
_REQUIRED_REASON_PATH = Path(__file__).resolve().parents[2] / "apple_rules" / "required_reason_apis.json"


def _load_short_codes() -> dict[str, str]:
    data = json.loads(_DATA_TYPE_CATALOG_PATH.read_text(encoding="utf-8"))
    return data["collected_data_type_short_codes"]


def _load_required_reason_categories() -> list[dict]:
    data = json.loads(_REQUIRED_REASON_PATH.read_text(encoding="utf-8"))
    return data["categories"]


COLLECTED_DATA_TYPE_SHORT_CODES = _load_short_codes()
REQUIRED_REASON_CATEGORIES = _load_required_reason_categories()

PURPOSE_MAP = {
    "NSPrivacyCollectedDataTypePurposeThirdPartyAdvertising": Purpose.THIRD_PARTY_ADVERTISING.value,
    "NSPrivacyCollectedDataTypePurposeDeveloperAdvertising": Purpose.DEVELOPER_ADVERTISING.value,
    "NSPrivacyCollectedDataTypePurposeAnalytics": Purpose.ANALYTICS.value,
    "NSPrivacyCollectedDataTypePurposeProductPersonalization": Purpose.PRODUCT_PERSONALIZATION.value,
    "NSPrivacyCollectedDataTypePurposeAppFunctionality": Purpose.APP_FUNCTIONALITY.value,
    "NSPrivacyCollectedDataTypePurposeOther": Purpose.OTHER.value,
}


class ManifestIssue:
    __slots__ = ("code", "severity", "message", "path")

    def __init__(self, code: str, severity: Severity | str, message: str, path: str) -> None:
        self.code = code
        self.severity = Severity(severity)
        self.message = message
        self.path = path

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity.value, "message": self.message, "path": self.path}


def _map_purposes(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [PURPOSE_MAP.get(item, Purpose.OTHER.value) for item in raw if isinstance(item, str)]


def _load_plist(path: Path):
    try:
        with path.open("rb") as handle:
            return plistlib.load(handle), None
    except FileNotFoundError:
        return None, "not_found"
    except (ValueError, plistlib.InvalidFileException, ExpatError, OSError) as exc:
        return None, str(exc)


def _validate_manifest(rel_path: str, data: dict, short_codes: dict[str, str]):
    evidence: list[PrivacyEvidence] = []
    issues: list[ManifestIssue] = []

    tracking_flag = data.get("NSPrivacyTracking")
    if "NSPrivacyTracking" in data and not isinstance(tracking_flag, bool):
        issues.append(ManifestIssue(
            "MANIFEST_INVALID_TRACKING_TYPE", Severity.HIGH,
            f"NSPrivacyTracking must be a boolean, found {type(tracking_flag).__name__}.", rel_path,
        ))
        tracking_flag = None
    tracking_tri = tri_state(tracking_flag) if tracking_flag is not None else TriState.UNKNOWN
    evidence.append(PrivacyEvidence(
        evidence_id=f"manifest:{rel_path}:tracking",
        kind="manifest_tracking_flag", source_type="PrivacyInfo.xcprivacy", source_path=rel_path,
        observed=tracking_flag, tracking=tracking_tri,
        confidence=Confidence.HIGH if tracking_flag is not None else Confidence.LOW,
        requires_user_confirmation=tracking_flag is None,
        notes=(
            "Declared NSPrivacyTracking flag from the local privacy manifest."
            if tracking_flag is not None else
            "NSPrivacyTracking is not declared in the local privacy manifest."
        ),
    ))

    domains = data.get("NSPrivacyTrackingDomains", [])
    if domains and not (isinstance(domains, list) and all(isinstance(item, str) for item in domains)):
        issues.append(ManifestIssue(
            "MANIFEST_INVALID_TRACKING_DOMAINS_TYPE", Severity.HIGH,
            "NSPrivacyTrackingDomains must be a list of strings.", rel_path,
        ))
        domains = []
    for domain in domains:
        evidence.append(PrivacyEvidence(
            evidence_id=f"manifest:{rel_path}:domain:{domain}",
            kind="manifest_tracking_domain", source_type="PrivacyInfo.xcprivacy", source_path=rel_path,
            observed=domain, tracking=TriState.UNKNOWN, confidence=Confidence.HIGH,
            requires_user_confirmation=True,
            notes=(
                "Tracking domain listed in the local privacy manifest; NSPrivacyTracking must "
                "also be true for consistency."
            ),
        ))
    if domains and tracking_tri is not TriState.YES:
        issues.append(ManifestIssue(
            "MANIFEST_TRACKING_DOMAIN_WITHOUT_FLAG", Severity.HIGH,
            "NSPrivacyTrackingDomains is populated but NSPrivacyTracking is not true.", rel_path,
        ))

    collected = data.get("NSPrivacyCollectedDataTypes", [])
    if collected and not isinstance(collected, list):
        issues.append(ManifestIssue(
            "MANIFEST_INVALID_COLLECTED_TYPES_SHAPE", Severity.HIGH,
            "NSPrivacyCollectedDataTypes must be a list.", rel_path,
        ))
        collected = []
    seen_types: set[str] = set()
    for index, entry in enumerate(collected):
        if not isinstance(entry, dict):
            issues.append(ManifestIssue(
                "MANIFEST_INVALID_COLLECTED_TYPE_ENTRY", Severity.HIGH,
                f"NSPrivacyCollectedDataTypes[{index}] must be a dictionary.", rel_path,
            ))
            continue
        apple_type = entry.get("NSPrivacyCollectedDataType")
        if not isinstance(apple_type, str) or not apple_type:
            issues.append(ManifestIssue(
                "MANIFEST_MISSING_DATA_TYPE", Severity.HIGH,
                f"NSPrivacyCollectedDataTypes[{index}] is missing NSPrivacyCollectedDataType.", rel_path,
            ))
            continue
        if apple_type not in short_codes:
            issues.append(ManifestIssue(
                "MANIFEST_UNKNOWN_DATA_TYPE", Severity.HIGH,
                f"Unknown NSPrivacyCollectedDataType value: {apple_type!r}.", rel_path,
            ))
        if apple_type in seen_types:
            issues.append(ManifestIssue(
                "MANIFEST_DUPLICATE_DATA_TYPE", Severity.MEDIUM,
                f"Duplicate NSPrivacyCollectedDataType entry: {apple_type!r}.", rel_path,
            ))
        seen_types.add(apple_type)

        linked = entry.get("NSPrivacyCollectedDataTypeLinked")
        if linked is not None and not isinstance(linked, bool):
            issues.append(ManifestIssue(
                "MANIFEST_INVALID_LINKED_TYPE", Severity.HIGH,
                f"NSPrivacyCollectedDataTypeLinked must be boolean for {apple_type!r}.", rel_path,
            ))
            linked = None
        entry_tracking = entry.get("NSPrivacyCollectedDataTypeTracking")
        if entry_tracking is not None and not isinstance(entry_tracking, bool):
            issues.append(ManifestIssue(
                "MANIFEST_INVALID_TRACKING_ENTRY_TYPE", Severity.HIGH,
                f"NSPrivacyCollectedDataTypeTracking must be boolean for {apple_type!r}.", rel_path,
            ))
            entry_tracking = None
        purposes = entry.get("NSPrivacyCollectedDataTypePurposes", [])
        if purposes and not (isinstance(purposes, list) and all(isinstance(item, str) for item in purposes)):
            issues.append(ManifestIssue(
                "MANIFEST_INVALID_PURPOSES_TYPE", Severity.HIGH,
                f"NSPrivacyCollectedDataTypePurposes must be a list of strings for {apple_type!r}.", rel_path,
            ))
            purposes = []

        evidence.append(PrivacyEvidence(
            evidence_id=f"manifest:{rel_path}:collected:{apple_type}",
            kind="manifest_collected_data_type", source_type="PrivacyInfo.xcprivacy", source_path=rel_path,
            observed=entry, data_type_candidate=short_codes.get(apple_type, apple_type),
            collection=TriState.YES,
            linked_to_user=tri_state(linked) if linked is not None else TriState.UNKNOWN,
            tracking=tri_state(entry_tracking) if entry_tracking is not None else TriState.UNKNOWN,
            purpose_candidates=tuple(_map_purposes(purposes)),
            confidence=Confidence.HIGH,
            requires_user_confirmation=False,
            notes=(
                "Declared as collected in the local privacy manifest; this is the developer's own "
                "declaration, not inferred."
            ),
        ))

    accessed = data.get("NSPrivacyAccessedAPITypes", [])
    if accessed and not isinstance(accessed, list):
        issues.append(ManifestIssue(
            "MANIFEST_INVALID_ACCESSED_API_SHAPE", Severity.HIGH,
            "NSPrivacyAccessedAPITypes must be a list.", rel_path,
        ))
        accessed = []
    for index, entry in enumerate(accessed):
        if not isinstance(entry, dict):
            issues.append(ManifestIssue(
                "MANIFEST_INVALID_ACCESSED_API_ENTRY", Severity.HIGH,
                f"NSPrivacyAccessedAPITypes[{index}] must be a dictionary.", rel_path,
            ))
            continue
        api_type = entry.get("NSPrivacyAccessedAPIType")
        reasons = entry.get("NSPrivacyAccessedAPITypeReasons", [])
        if not isinstance(api_type, str) or not api_type:
            issues.append(ManifestIssue(
                "MANIFEST_MISSING_ACCESSED_API_TYPE", Severity.HIGH,
                f"NSPrivacyAccessedAPITypes[{index}] is missing NSPrivacyAccessedAPIType.", rel_path,
            ))
            continue
        if not (isinstance(reasons, list) and reasons and all(isinstance(item, str) for item in reasons)):
            issues.append(ManifestIssue(
                "MANIFEST_MISSING_ACCESSED_API_REASON", Severity.HIGH,
                f"NSPrivacyAccessedAPITypes entry {api_type!r} must declare at least one reason.", rel_path,
            ))
            reasons = []
        evidence.append(PrivacyEvidence(
            evidence_id=f"manifest:{rel_path}:api:{api_type}",
            kind="manifest_required_reason_entry", source_type="PrivacyInfo.xcprivacy", source_path=rel_path,
            observed={"type": api_type, "reasons": reasons}, confidence=Confidence.HIGH,
            requires_user_confirmation=False,
            notes=f"Declared required-reason API category {api_type!r} with reason(s) {reasons}.",
        ))

    return evidence, issues


def inspect(inspector: ProjectInspector):
    all_evidence: list[PrivacyEvidence] = []
    all_issues: list[ManifestIssue] = []
    for path in inspector.files(("**/PrivacyInfo.xcprivacy",)):
        rel_path = inspector.relative(path)
        data, error = _load_plist(path)
        if error is not None:
            all_issues.append(ManifestIssue(
                "MANIFEST_UNPARSEABLE", Severity.HIGH, f"Could not parse privacy manifest: {error}", rel_path,
            ))
            continue
        if not isinstance(data, dict):
            all_issues.append(ManifestIssue(
                "MANIFEST_INVALID_ROOT_TYPE", Severity.HIGH, "Privacy manifest root must be a dictionary.", rel_path,
            ))
            continue
        evidence, issues = _validate_manifest(rel_path, data, COLLECTED_DATA_TYPE_SHORT_CODES)
        all_evidence.extend(evidence)
        all_issues.extend(issues)
    return all_evidence, all_issues


def inspect_required_reason_apis(inspector: ProjectInspector, manifest_evidence: list[PrivacyEvidence]):
    """Conservative, text-match-only detection of required-reason API usage,
    cross-checked against manifest-declared categories.

    This never claims full static/binary-analysis coverage: a category with
    no conservative text match is left UNKNOWN (REASON_UNVERIFIED), never
    treated as proof of absence. A category that *is* detected in source
    with no matching manifest reason is a deterministic gap (both the
    source match and the manifest absence are directly observable), so it
    may legitimately be reported as a BLOCKED-severity issue.
    """
    declared_categories = {
        item.observed["type"] for item in manifest_evidence
        if item.kind == "manifest_required_reason_entry" and isinstance(item.observed, dict)
    }
    code_files = [p for p in inspector.all_text_files() if p.suffix.lower() in {".dart", ".swift", ".m", ".mm"}]

    evidence: list[PrivacyEvidence] = []
    issues: list[ManifestIssue] = []
    for entry in REQUIRED_REASON_CATEGORIES:
        matches = inspector.search(entry["detection_pattern"], code_files)
        if not matches:
            continue
        path, line, text = matches[0]
        rel_path = inspector.relative(path)
        manifest_key = entry["manifest_key"]
        if manifest_key in declared_categories:
            evidence.append(PrivacyEvidence(
                evidence_id=f"required_reason:{entry['category']}:present",
                kind="required_reason_api_manifest_reason_present",
                source_type="source+manifest", source_path=rel_path, observed=text,
                confidence=Confidence.HIGH, requires_user_confirmation=False,
                notes=(
                    f"Detected {entry['category']} API usage in source, matched by a declared "
                    f"{manifest_key} reason in the local privacy manifest."
                ),
            ))
        else:
            issues.append(ManifestIssue(
                "MANIFEST_REASON_MISSING", Severity.HIGH,
                f"Detected {entry['category']} API usage in source ({rel_path}:{line}) with no "
                f"matching {manifest_key} entry in any local privacy manifest.", rel_path,
            ))
            evidence.append(PrivacyEvidence(
                evidence_id=f"required_reason:{entry['category']}:missing",
                kind="required_reason_api_detected",
                source_type="source", source_path=rel_path, observed=text,
                confidence=Confidence.HIGH, requires_user_confirmation=False,
                notes=f"Detected {entry['category']} API usage in source with no corresponding manifest reason declared.",
            ))
    # Always disclosed, regardless of whether some categories matched: a
    # conservative text scan of a subset of known categories is never a claim
    # of complete static/binary-analysis coverage of required-reason API use.
    evidence.append(PrivacyEvidence(
        evidence_id="required_reason:unverified",
        kind="required_reason_unverified",
        source_type="source", observed="conservative text-match scan only",
        confidence=Confidence.LOW, requires_user_confirmation=True,
        notes=(
            "Required-reason API usage was checked only via a conservative text scan of a known "
            "category list; this is not a claim of complete static/binary-analysis coverage."
        ),
    ))
    return evidence, issues
