"""Draft a concise, structured reply to Apple.

The body never contains a "fixed"/"resolved" style claim except through a
Claim object whose wording is templated from its ClaimStatus (see
models.py) -- so an UNVERIFIED root cause structurally cannot produce
"we fixed it" language. ready_to_send is likewise derived, never set
directly. Nothing here sends anything.
"""

from __future__ import annotations

from .models import (
    Claim, ClaimStatus, RejectionMessage, ReplyDraft, ResponseMode, RootCauseCandidate,
    RootCauseStatus, VerificationResult,
)
from .parser import redact_secrets

_EXCERPT_LIMIT = 400


def _claim_kind(root_cause: RootCauseCandidate, verification: VerificationResult) -> str:
    if verification.claim_status is ClaimStatus.VERIFIED and root_cause.status is RootCauseStatus.CONTRADICTED:
        return "dispute"
    if verification.claim_status in (ClaimStatus.VERIFIED, ClaimStatus.USER_ATTESTED):
        return "fix"
    return "clarification"


def _response_mode(claims: list[Claim]) -> ResponseMode:
    if not claims:
        return ResponseMode.CLARIFICATION
    kinds = {claim.kind for claim in claims}
    statuses = {claim.status for claim in claims}
    if kinds == {"dispute"} and statuses == {ClaimStatus.VERIFIED}:
        return ResponseMode.DISPUTE_WITH_EVIDENCE
    if kinds == {"clarification"}:
        return ResponseMode.CLARIFICATION
    resolved = {ClaimStatus.VERIFIED, ClaimStatus.USER_ATTESTED}
    if statuses <= resolved:
        return ResponseMode.FIXED
    if statuses & resolved:
        return ResponseMode.PARTIALLY_FIXED
    return ResponseMode.CLARIFICATION


def draft_reply(
    rejection: RejectionMessage, root_causes: list[RootCauseCandidate],
    verification_results: list[VerificationResult], *, language: str = "en",
) -> ReplyDraft:
    by_root_cause = {vr.root_cause_id: vr for vr in verification_results}
    claims: list[Claim] = []
    for root_cause in root_causes:
        verification = by_root_cause.get(root_cause.root_cause_id)
        if verification is None:
            continue
        kind = _claim_kind(root_cause, verification)
        claims.append(Claim(
            claim_id=f"claim:{root_cause.root_cause_id}", subject=root_cause.title.lower(), kind=kind,
            status=verification.claim_status,
            evidence_refs=(root_cause.root_cause_id, verification.verification_id) + root_cause.related_findings,
        ))

    mode = _response_mode(claims)
    excerpt = redact_secrets(rejection.raw_text.strip())[:_EXCERPT_LIMIT]

    lines = [
        f"Apple's concern (as reported): {excerpt}",
        "",
        "Our response:",
    ]
    lines.extend(f"- {claim.statement}" for claim in claims)
    if any(claim.status is ClaimStatus.UNVERIFIED for claim in claims):
        lines += [
            "",
            "We would appreciate any additional detail App Review can share (e.g. the exact device/OS "
            "version, steps taken, or screenshot) so we can confirm and address this precisely.",
        ]

    subject = f"Re: App Review rejection {rejection.rejection_id} ({rejection.review_state})"
    evidence_refs = tuple(dict.fromkeys(ref for claim in claims for ref in claim.evidence_refs))

    return ReplyDraft(
        draft_id=f"reply:{rejection.rejection_id}", rejection_id=rejection.rejection_id, language=language,
        subject=subject, body="\n".join(lines), claims=tuple(claims), response_mode=mode,
        evidence_refs=evidence_refs, requires_user_review=True,
    )
