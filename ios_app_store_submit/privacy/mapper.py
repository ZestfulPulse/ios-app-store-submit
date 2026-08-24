"""Aggregate raw PrivacyEvidence into per-data-type PrivacyCandidate objects.

Aggregation never invents a fact: a field on the resulting candidate is
only ever as resolved as the most specific evidence backing it. Absence of
a signal for a field keeps it UNKNOWN, and a candidate can only become
CONFIRMED when every fact it carries is backed by deterministic evidence
(a local privacy manifest declaration or an explicit developer
attestation) with no conflicting evidence for the same field.
"""

from __future__ import annotations

from collections import defaultdict

from .models import CandidateState, Confidence, PrivacyCandidate, PrivacyEvidence, TriState

DETERMINISTIC_KINDS = {
    "manifest_collected_data_type", "manifest_tracking_flag", "manifest_tracking_domain",
    "local_privacy_answer_attestation",
}


def _has_conflict(items: list[PrivacyEvidence], field: str) -> bool:
    values = {getattr(item, field) for item in items}
    return TriState.YES in values and TriState.NO in values


def _merge(items: list[PrivacyEvidence], field: str) -> TriState:
    if _has_conflict(items, field):
        return TriState.UNKNOWN
    values = {getattr(item, field) for item in items}
    if TriState.YES in values:
        return TriState.YES
    if TriState.NO in values:
        return TriState.NO
    return TriState.UNKNOWN


def build_candidates(evidence: list[PrivacyEvidence]) -> list[PrivacyCandidate]:
    grouped: dict[str, list[PrivacyEvidence]] = defaultdict(list)
    for item in evidence:
        if item.data_type_candidate:
            grouped[item.data_type_candidate].append(item)

    candidates: list[PrivacyCandidate] = []
    for data_type, items in sorted(grouped.items()):
        collection = _merge(items, "collection")
        linked = _merge(items, "linked_to_user")
        tracking = _merge(items, "tracking")
        purposes = tuple(sorted({purpose for item in items for purpose in item.purpose_candidates}))
        evidence_ids = tuple(item.evidence_id for item in items)
        conflict = _has_conflict(items, "collection") or _has_conflict(items, "tracking") or _has_conflict(items, "linked_to_user")
        all_deterministic = all(item.kind in DETERMINISTIC_KINDS for item in items)
        unresolved = TriState.UNKNOWN in (collection, linked, tracking)
        requires_confirmation = unresolved or conflict or any(item.requires_user_confirmation for item in items)

        if conflict:
            state = CandidateState.UNKNOWN
            confidence = Confidence.LOW
        elif all_deterministic and not unresolved:
            state = CandidateState.CONFIRMED
            confidence = Confidence.HIGH
        elif not unresolved:
            state = CandidateState.LIKELY
            confidence = Confidence.MEDIUM
        elif any(item.confidence is Confidence.MEDIUM for item in items):
            state = CandidateState.POSSIBLE
            confidence = Confidence.MEDIUM
        else:
            state = CandidateState.UNKNOWN
            confidence = Confidence.LOW

        missing = [name for name, value in (
            ("whether it is transmitted off-device and retained", collection),
            ("whether it is linked to an identifiable user", linked),
            ("whether it is used for tracking", tracking),
        ) if value is TriState.UNKNOWN]
        label = data_type.replace("_", " ").title()
        if missing:
            recommended_action = f"Ask {', and '.join(missing)} for {label}."
        else:
            recommended_action = f"No open question remains for {label} from local evidence alone."

        candidates.append(PrivacyCandidate(
            candidate_id=f"candidate:{data_type}",
            apple_data_type=data_type,
            state=state,
            collection=collection,
            linked_to_user=linked,
            tracking=tracking,
            purpose_candidates=purposes,
            confidence=confidence,
            evidence_ids=evidence_ids,
            contradictions=(),
            requires_user_confirmation=requires_confirmation,
            recommended_action=recommended_action,
        ))
    return candidates
