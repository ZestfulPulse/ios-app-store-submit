"""Eligibility gate for a recovered App Store rejection.

This module consumes Phase 6 output and never contacts App Store Connect.  A
conditional result is deliberately narrower than a pass: it means the only
remaining evidence is outside the local machine (runtime, user confirmation,
or ASC state).
"""

from __future__ import annotations

from typing import Any, Mapping

from .models import ApprovalDecision, EligibilityResult, ResubmitStatus, as_mapping


_CONDITIONAL_REASONS = {"requires_runtime", "requires_user_confirmation", "asc_only", "user_confirmation"}


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _items(value: Any) -> list[Any]:
    return list(value or ())


def _has_blocked_finding(value: Any, *, in_finding_collection: bool = False) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            collection = in_finding_collection or key in {
                "findings", "review_findings", "privacy_findings", "design_findings", "unresolved_findings",
            }
            if collection and isinstance(child, list):
                if any(str(_value(item, "status", "")).upper() == "BLOCKED" for item in child):
                    return True
            if _has_blocked_finding(child, in_finding_collection=collection):
                return True
    elif isinstance(value, list):
        return any(_has_blocked_finding(item, in_finding_collection=in_finding_collection) for item in value)
    return False


def evaluate_eligibility(recovery_result: Any, *, approval: Any = None) -> EligibilityResult:
    """Evaluate the Phase 7 technical/reviewer gate from Phase 6 output.

    Approval is reported separately by the approval gate.  Passing this
    function never means that submission may execute.
    """

    raw = as_mapping(recovery_result)
    if raw is None:
        return EligibilityResult(ResubmitStatus.NO, ("missing_recovery_result",))

    summary = raw.get("recovery_summary", {})
    if not summary and not raw.get("reply_drafts") and not raw.get("verification_results"):
        return EligibilityResult(ResubmitStatus.NO, ("missing_recovery_result",))

    blockers: set[str] = set()
    conditional: set[str] = set()
    candidate = str(summary.get("resubmit_candidate", raw.get("resubmit_candidate", "NO"))).upper()
    if candidate == ResubmitStatus.NO.value:
        blockers.add("phase6_recovery_not_eligible")
    elif candidate == ResubmitStatus.CONDITIONAL.value:
        conditional.add("phase6_external_evidence_pending")

    verification_results = _items(raw.get("verification_results"))
    if not verification_results:
        blockers.add("missing_recovery_verification")
    for result in verification_results:
        status = str(_value(result, "claim_status", "UNVERIFIED")).upper()
        reason = str(_value(result, "pending_reason", "") or "").lower()
        if status == "FORBIDDEN_TO_CLAIM":
            blockers.add("forbidden_claim")
        elif status in {"UNVERIFIED", "UNKNOWN"}:
            if reason in _CONDITIONAL_REASONS:
                conditional.add(reason)
            else:
                blockers.add("unverified_machine_issue")
        elif status not in {"VERIFIED", "USER_ATTESTED"}:
            blockers.add("unverified_machine_issue")

    for root_cause in _items(raw.get("root_causes")):
        status = str(_value(root_cause, "status", "UNKNOWN")).upper()
        root_id = _value(root_cause, "root_cause_id", "")
        matching = next(
            (item for item in verification_results if _value(item, "root_cause_id", "") == root_id), None
        )
        matching_status = str(_value(matching, "claim_status", "") or "").upper()
        if status == "CONTRADICTED" and matching_status not in {"VERIFIED", "USER_ATTESTED"}:
            blockers.add("unresolved_contradiction")
        if bool(_value(root_cause, "requires_runtime", False)) and matching_status not in {"VERIFIED", "USER_ATTESTED"}:
            conditional.add("requires_runtime")
        if bool(_value(root_cause, "requires_user_confirmation", False)) and matching_status not in {"VERIFIED", "USER_ATTESTED"}:
            conditional.add("requires_user_confirmation")

    drafts = _items(raw.get("reply_drafts"))
    draft = drafts[0] if drafts else None
    ready_to_send = bool(_value(draft, "ready_to_send", False))
    if not ready_to_send:
        if any(reason in _CONDITIONAL_REASONS for reason in conditional):
            pass
        else:
            blockers.add("reply_not_ready")
    for claim in _items(_value(draft, "claims", ())):
        if str(_value(claim, "status", "")).upper() == "FORBIDDEN_TO_CLAIM":
            blockers.add("forbidden_claim")

    # Phase 6 callers may attach explicit current-state audit fields.  These
    # are consumed defensively so a stale local report cannot be submitted.
    if any(bool(raw.get(key)) for key in ("stale_build_version", "stale_version", "stale_build", "build_version_stale")):
        blockers.add("stale_build_version")
    if any(str(raw.get(key, "")).upper() == "STALE" for key in ("version_state", "build_state", "build_version_state")):
        blockers.add("stale_build_version")
    if raw.get("unresolved_blocked_findings"):
        blockers.add("unresolved_blocked_findings")
    if _has_blocked_finding(raw):
        blockers.add("unresolved_blocked_findings")
    if raw.get("unresolved_contradictions"):
        blockers.add("unresolved_contradiction")
    if raw.get("privacy_contradictions") or raw.get("contradictions"):
        blockers.add("unresolved_contradiction")
    if raw.get("forbidden_claims"):
        blockers.add("forbidden_claim")

    if approval is not None:
        decision = approval if isinstance(approval, ApprovalDecision) else str(_value(approval, "decision", approval)).upper()
        if decision in {ApprovalDecision.REJECTED.value, ApprovalDecision.STALE.value}:
            blockers.add("invalid_resubmit_approval")

    report_id = (
        str(raw.get("recovery_report_id")) if raw.get("recovery_report_id") is not None
        else str(raw.get("rejection_input", {}).get("rejection_id", "")) or None
    )
    if blockers:
        return EligibilityResult(ResubmitStatus.NO, tuple(blockers), tuple(conditional), report_id)
    if conditional:
        return EligibilityResult(ResubmitStatus.CONDITIONAL, (), tuple(conditional), report_id)
    return EligibilityResult(ResubmitStatus.YES, (), (), report_id)


def assess_eligibility(recovery_result: Any, **kwargs: Any) -> EligibilityResult:
    return evaluate_eligibility(recovery_result, **kwargs)


def check_eligibility(recovery_result: Any, **kwargs: Any) -> EligibilityResult:
    return evaluate_eligibility(recovery_result, **kwargs)


def check_resubmit_eligibility(recovery_result: Any, **kwargs: Any) -> EligibilityResult:
    return evaluate_eligibility(recovery_result, **kwargs)


def evaluate_resubmit_eligibility(recovery_result: Any, **kwargs: Any) -> EligibilityResult:
    return evaluate_eligibility(recovery_result, **kwargs)


__all__ = [
    "assess_eligibility", "check_eligibility", "check_resubmit_eligibility",
    "evaluate_eligibility", "evaluate_resubmit_eligibility",
]
