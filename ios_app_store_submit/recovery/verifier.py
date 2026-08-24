"""Re-check whether a root cause's underlying finding still holds.

This never applies a fix -- it only re-runs (via the Phase 3/4/5 result
objects a caller passes in) and compares the current state against what the
root cause originally cited. A claim can only become VERIFIED when that
recheck deterministically shows PASS through the SAME engine that owns the
category; it is never inferred from a fix "having been attempted."

Two categories (PAYMENTS_IAP, LEGAL_POLICY) can never be claimed resolved
without an explicit human attestation, regardless of any local recheck --
compliance in those areas is a human/legal judgment this tool must not make.
"""

from __future__ import annotations

from ..readiness.models import Evidence
from .models import ClaimStatus, RootCauseCandidate, RootCauseCategory, VerificationResult
from .root_cause import category_recheck_status

_NEVER_CLAIMABLE_WITHOUT_ATTESTATION = {RootCauseCategory.PAYMENTS_IAP, RootCauseCategory.LEGAL_POLICY}


def verify_root_cause(
    root_cause: RootCauseCandidate, *, pre_review_result=None, privacy_result=None, design_result=None,
    attestations: dict | None = None,
) -> VerificationResult:
    attestations = attestations or {}
    attestation = attestations.get(root_cause.category.value) or attestations.get(root_cause.root_cause_id)
    attested = bool(attestation) and attestation.get("attested") is True

    if attested:
        return VerificationResult(
            verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
            claim_status=ClaimStatus.USER_ATTESTED, pending_reason=None, rechecked_rule_ids=(),
            message=f"The developer attested that this {root_cause.category.value.lower()} issue is resolved.",
            evidence=(Evidence(kind="attestation", observed=attestation.get("note", "attested"), source="user"),),
        )

    if root_cause.category in _NEVER_CLAIMABLE_WITHOUT_ATTESTATION:
        return VerificationResult(
            verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
            claim_status=ClaimStatus.FORBIDDEN_TO_CLAIM, pending_reason=None, rechecked_rule_ids=(),
            message=f"{root_cause.category.value} concerns require explicit human sign-off before any "
                    "claim can be made; none was given.",
            evidence=(),
        )

    recheck = category_recheck_status(
        root_cause.category, pre_review_result=pre_review_result, privacy_result=privacy_result,
        design_result=design_result,
    )
    if recheck == "PASS":
        return VerificationResult(
            verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
            claim_status=ClaimStatus.VERIFIED, pending_reason=None,
            rechecked_rule_ids=root_cause.related_findings,
            message=f"Re-running the {root_cause.category.value.lower()} check now shows PASS.",
            evidence=(Evidence(kind="recheck", observed="PASS", source="local re-check"),),
        )
    if recheck == "BLOCKED":
        return VerificationResult(
            verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
            claim_status=ClaimStatus.UNVERIFIED, pending_reason="still_blocked",
            rechecked_rule_ids=root_cause.related_findings,
            message=f"Re-running the {root_cause.category.value.lower()} check still shows BLOCKED.",
            evidence=(Evidence(kind="recheck", observed="BLOCKED", source="local re-check"),),
        )
    if root_cause.requires_runtime:
        return VerificationResult(
            verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
            claim_status=ClaimStatus.UNVERIFIED, pending_reason="requires_runtime", rechecked_rule_ids=(),
            message="This requires device/simulator runtime evidence, which Phase 6 does not capture.",
            evidence=(),
        )
    if root_cause.requires_user_confirmation:
        return VerificationResult(
            verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
            claim_status=ClaimStatus.UNVERIFIED, pending_reason="requires_user_confirmation", rechecked_rule_ids=(),
            message="This requires explicit developer confirmation before it can be claimed resolved.",
            evidence=(),
        )
    return VerificationResult(
        verification_id=f"verify:{root_cause.root_cause_id}", root_cause_id=root_cause.root_cause_id,
        claim_status=ClaimStatus.UNVERIFIED, pending_reason="still_blocked", rechecked_rule_ids=(),
        message="No local re-check evidence is available to support a resolution claim.",
        evidence=(),
    )


def verify_root_causes(
    root_causes: list[RootCauseCandidate], *, pre_review_result=None, privacy_result=None, design_result=None,
    attestations: dict | None = None,
) -> list[VerificationResult]:
    return [
        verify_root_cause(
            root_cause, pre_review_result=pre_review_result, privacy_result=privacy_result,
            design_result=design_result, attestations=attestations,
        )
        for root_cause in root_causes
    ]
