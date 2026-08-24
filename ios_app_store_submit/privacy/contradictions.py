"""Detect conflicts between distinct pieces of privacy evidence.

A contradiction is never silently resolved: it is always surfaced in the
report and always forces at least a CONDITIONAL privacy gate.
"""

from __future__ import annotations

from .manifest import ManifestIssue
from .models import Contradiction, PrivacyEvidence, Severity, TriState

_ADVERTISING_OR_ANALYTICS_PURPOSES = {"ANALYTICS", "THIRD_PARTY_ADVERTISING", "DEVELOPER_ADVERTISING"}
_TRI_FIELDS = (("collection", "collection"), ("tracking", "tracking"), ("linked_to_user", "linkage"))


def _pair(items: list[PrivacyEvidence], field: str):
    yes_items = [item for item in items if getattr(item, field) is TriState.YES]
    no_items = [item for item in items if getattr(item, field) is TriState.NO]
    return yes_items, no_items


def find_contradictions(
    evidence: list[PrivacyEvidence], manifest_issues: list[ManifestIssue] = (),
) -> list[Contradiction]:
    contradictions: list[Contradiction] = []

    grouped: dict[str, list[PrivacyEvidence]] = {}
    for item in evidence:
        if item.data_type_candidate:
            grouped.setdefault(item.data_type_candidate, []).append(item)

    for data_type, items in sorted(grouped.items()):
        for field, label in _TRI_FIELDS:
            yes_items, no_items = _pair(items, field)
            if yes_items and no_items:
                contradictions.append(Contradiction(
                    contradiction_id=f"contradiction:{data_type}:{field}:{len(contradictions)}",
                    kind=f"{label.upper()}_CONFLICT",
                    severity=Severity.HIGH,
                    evidence_left=yes_items[0].evidence_id,
                    evidence_right=no_items[0].evidence_id,
                    message=f"Evidence conflicts on whether {data_type} has {label}=YES vs {label}=NO.",
                    requested_resolution=(
                        f"Resolve the actual {label} status of {data_type} before publishing an App "
                        "Privacy answer for it."
                    ),
                ))

    for issue in manifest_issues:
        if issue.code == "MANIFEST_TRACKING_DOMAIN_WITHOUT_FLAG":
            contradictions.append(Contradiction(
                contradiction_id=f"contradiction:manifest:{issue.path}:{len(contradictions)}",
                kind="TRACKING_DOMAIN_WITHOUT_FLAG",
                severity=Severity.HIGH,
                evidence_left=f"manifest:{issue.path}:tracking",
                evidence_right=None,
                message=issue.message,
                requested_resolution="Either set NSPrivacyTracking to true or remove the tracking domain(s).",
            ))

    sdk_purposes: dict[str, list[PrivacyEvidence]] = {}
    for item in evidence:
        if item.kind == "sdk_dependency":
            for purpose in item.purpose_candidates:
                sdk_purposes.setdefault(purpose, []).append(item)
    manifest_purposes = {
        purpose for item in evidence if item.kind == "manifest_collected_data_type" for purpose in item.purpose_candidates
    }
    for purpose, items in sorted(sdk_purposes.items()):
        if purpose not in _ADVERTISING_OR_ANALYTICS_PURPOSES or purpose in manifest_purposes:
            continue
        for item in items:
            contradictions.append(Contradiction(
                contradiction_id=f"contradiction:sdk:{item.evidence_id}:{len(contradictions)}",
                kind="SDK_WITHOUT_PRIVACY_EVIDENCE",
                severity=Severity.MEDIUM,
                evidence_left=item.evidence_id,
                evidence_right=None,
                message=(
                    f"{item.observed} suggests {purpose.replace('_', ' ').title()} data handling, but "
                    "no local privacy manifest entry covers that purpose."
                ),
                requested_resolution="Confirm whether this SDK's data handling should be reflected in the App Privacy declaration.",
            ))

    # Scoped to permission-declaration evidence only: that is the one kind that
    # always speaks to all three facts (collection/tracking/linkage) for a real
    # data type at once. Single-purpose manifest entries (a tracking flag alone,
    # a tracking domain alone) legitimately leave the other two fields UNKNOWN
    # without needing confirmation, since they never claimed anything about them.
    for item in evidence:
        if item.kind != "permission_declaration":
            continue
        unresolved = TriState.UNKNOWN in (item.collection, item.tracking, item.linked_to_user)
        if unresolved and not item.requires_user_confirmation:
            contradictions.append(Contradiction(
                contradiction_id=f"contradiction:unconfirmed:{item.evidence_id}",
                kind="UNCONFIRMED_SENSITIVE_EVIDENCE",
                severity=Severity.HIGH,
                evidence_left=item.evidence_id,
                evidence_right=None,
                message=f"{item.evidence_id} has unresolved privacy facts but does not request user confirmation.",
                requested_resolution="Flag this evidence as requiring user confirmation before any App Privacy answer is drafted.",
            ))

    return contradictions
