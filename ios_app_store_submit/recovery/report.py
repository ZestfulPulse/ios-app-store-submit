"""Orchestrates the Phase 6 pipeline: parse -> map -> root-cause -> plan ->
verify -> reply -> resubmit-candidate, into one RecoveryResult.

RESUBMIT_CANDIDATE=YES never submits anything -- it is a read-only
assessment, exactly like every other phase's gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..design.evaluator import DesignReviewResult
from ..privacy.report import PrivacyIntelligenceResult
from ..readiness.models import ReadinessReport
from ..readiness.report import build_report
from ..review.evaluator import PreReviewResult, run_pre_review
from .mapper import map_rejection
from .models import (
    ClaimStatus, RecoveryFixPlan, ReplyDraft, RootCauseCandidate, RootCauseStatus, RuleMapping,
    VerificationResult,
)
from .parser import parse_rejection_file, redacted_rejection_dict
from .planner import plan_recovery_fixes
from .reply import draft_reply
from .root_cause import analyze_root_causes
from .verifier import verify_root_causes


def _load_attestations(project_root: Path) -> dict:
    path = project_root / ".asc" / "recovery_attestations.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("root_causes", {}) if isinstance(data, dict) else {}


def _compute_resubmit_candidate(
    root_causes: list[RootCauseCandidate], verification_results: list[VerificationResult],
    reply_draft: ReplyDraft, *, blocked_elsewhere: bool,
) -> str:
    if blocked_elsewhere:
        return "NO"
    if any(vr.claim_status is ClaimStatus.FORBIDDEN_TO_CLAIM for vr in verification_results):
        return "NO"
    by_id = {vr.root_cause_id: vr for vr in verification_results}
    unresolved_contradiction = any(
        rc.status is RootCauseStatus.CONTRADICTED
        and by_id.get(rc.root_cause_id) is not None
        and by_id[rc.root_cause_id].claim_status is not ClaimStatus.VERIFIED
        for rc in root_causes
    )
    if unresolved_contradiction:
        return "NO"
    if any(vr.pending_reason == "still_blocked" for vr in verification_results):
        return "NO"
    if any(vr.pending_reason in ("requires_runtime", "requires_user_confirmation", "asc_only")
           for vr in verification_results):
        return "CONDITIONAL"
    if reply_draft.ready_to_send:
        return "YES"
    return "NO"


_PRE_REVIEW_CATEGORIES = ("PERFORMANCE", "METADATA", "REVIEW_ACCESS", "PRIVACY")


def _has_orphaned_blocker(
    root_causes: list[RootCauseCandidate], *, pre_review_result, privacy_result=None, design_result=None,
) -> bool:
    """True when some BLOCKED category exists that no root cause accounts
    for at all -- i.e. a blocker Phase 6 never even looked at, as opposed
    to the exact blocker a root cause already tracks (which the normal
    per-root-cause verification/pending_reason logic already governs, so a
    USER_ATTESTED or VERIFIED resolution for it must not be double-blocked
    here)."""
    covered = {rc.category.value for rc in root_causes}
    for category in _PRE_REVIEW_CATEGORIES:
        if pre_review_result.category_status.get(category) == "BLOCKED" and category not in covered:
            return True
    if privacy_result is not None and privacy_result.gate == "BLOCKED" and "PRIVACY" not in covered:
        return True
    if design_result is not None and design_result.gate == "BLOCKED" and "DESIGN_HIG" not in covered:
        return True
    return False


def _reply_status(reply_draft: ReplyDraft) -> str:
    if any(claim.status is ClaimStatus.FORBIDDEN_TO_CLAIM for claim in reply_draft.claims):
        return "NOT_READY"
    if reply_draft.ready_to_send:
        return "READY"
    return "NEEDS_REVIEW"


@dataclass(frozen=True)
class RecoveryResult:
    rejection_dict: dict[str, Any]
    mappings: tuple[RuleMapping, ...] | list[RuleMapping]
    root_causes: tuple[RootCauseCandidate, ...] | list[RootCauseCandidate]
    fix_plans: tuple[RecoveryFixPlan, ...] | list[RecoveryFixPlan]
    verification_results: tuple[VerificationResult, ...] | list[VerificationResult]
    reply_draft: ReplyDraft
    resubmit_candidate: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "mappings", tuple(self.mappings))
        object.__setattr__(self, "root_causes", tuple(self.root_causes))
        object.__setattr__(self, "fix_plans", tuple(self.fix_plans))
        object.__setattr__(self, "verification_results", tuple(self.verification_results))

    def ordered_mappings(self):
        return tuple(sorted(self.mappings, key=lambda item: item.mapping_id))

    def ordered_root_causes(self):
        return tuple(sorted(self.root_causes, key=lambda item: item.root_cause_id))

    def ordered_fix_plans(self):
        return tuple(sorted(self.fix_plans, key=lambda item: item.fix_id))

    def ordered_verification_results(self):
        return tuple(sorted(self.verification_results, key=lambda item: item.verification_id))

    @property
    def reply_status(self) -> str:
        return _reply_status(self.reply_draft)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejection_input": self.rejection_dict,
            "rejection_parsed": self.rejection_dict,
            "rule_mappings": [item.to_dict() for item in self.ordered_mappings()],
            "root_causes": [item.to_dict() for item in self.ordered_root_causes()],
            "recovery_fix_plans": [item.to_dict() for item in self.ordered_fix_plans()],
            "verification_results": [item.to_dict() for item in self.ordered_verification_results()],
            "reply_drafts": [self.reply_draft.to_dict()],
            "recovery_summary": {
                "reply_status": self.reply_status,
                "resubmit_candidate": self.resubmit_candidate,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecoveryResult":
        summary = data.get("recovery_summary", {})
        reply_drafts = data.get("reply_drafts", [])
        return cls(
            rejection_dict=dict(data.get("rejection_input", {})),
            mappings=tuple(RuleMapping.from_dict(item) for item in data.get("rule_mappings", [])),
            root_causes=tuple(RootCauseCandidate.from_dict(item) for item in data.get("root_causes", [])),
            fix_plans=tuple(RecoveryFixPlan.from_dict(item) for item in data.get("recovery_fix_plans", [])),
            verification_results=tuple(
                VerificationResult.from_dict(item) for item in data.get("verification_results", [])
            ),
            reply_draft=ReplyDraft.from_dict(reply_drafts[0]) if reply_drafts else _empty_reply_draft(),
            resubmit_candidate=summary.get("resubmit_candidate", "NO"),
        )


def _empty_reply_draft() -> ReplyDraft:
    return ReplyDraft(
        draft_id="reply:empty", rejection_id="", language="en", subject="", body="", claims=(),
        response_mode="CLARIFICATION", evidence_refs=(), requires_user_review=True,
    )


def run_recovery(
    project_path: str | Path, rejection_path: str | Path, *, readiness_report: ReadinessReport | None = None,
    privacy_result: PrivacyIntelligenceResult | None = None, design_result: DesignReviewResult | None = None,
    pre_review_result: PreReviewResult | None = None,
) -> RecoveryResult:
    project_root = Path(project_path).expanduser().resolve()
    rejection = parse_rejection_file(rejection_path)

    # Phase 6 always needs Phase 3's category rollup (it owns guideline-number
    # mapping and the METADATA/PERFORMANCE/REVIEW_ACCESS/PRIVACY verdicts),
    # regardless of whether the caller separately asked to print --pre-review.
    readiness_report = readiness_report or build_report(project_root)
    pre_review_result = pre_review_result or run_pre_review(project_root, readiness_report=readiness_report)

    mappings = map_rejection(rejection)
    root_causes = analyze_root_causes(
        rejection, mappings, pre_review_result=pre_review_result, privacy_result=privacy_result,
        design_result=design_result,
    )
    fix_plans = plan_recovery_fixes(root_causes)
    attestations = _load_attestations(project_root)
    verification_results = verify_root_causes(
        root_causes, pre_review_result=pre_review_result, privacy_result=privacy_result,
        design_result=design_result, attestations=attestations,
    )
    reply_draft = draft_reply(rejection, root_causes, verification_results)

    blocked_elsewhere = _has_orphaned_blocker(
        root_causes, pre_review_result=pre_review_result, privacy_result=privacy_result, design_result=design_result,
    )
    resubmit_candidate = _compute_resubmit_candidate(
        root_causes, verification_results, reply_draft, blocked_elsewhere=blocked_elsewhere,
    )

    return RecoveryResult(
        rejection_dict=redacted_rejection_dict(rejection), mappings=mappings, root_causes=root_causes,
        fix_plans=fix_plans, verification_results=verification_results, reply_draft=reply_draft,
        resubmit_candidate=resubmit_candidate,
    )


def _root_cause_summary(root_causes) -> str:
    if not root_causes:
        return "none"
    priority = {"CONFIRMED": 0, "CONTRADICTED": 1, "LIKELY": 2, "POSSIBLE": 3, "UNKNOWN": 4}
    worst = min(root_causes, key=lambda rc: priority.get(rc.status.value, 5))
    return worst.status.value.lower()


def _fix_status_summary(fix_plans, verification_results) -> str:
    if not fix_plans:
        return "none"
    by_root_cause = {vr.root_cause_id: vr for vr in verification_results}
    statuses = {by_root_cause[p.root_cause_id].claim_status for p in fix_plans if p.root_cause_id in by_root_cause}
    if statuses and statuses <= {ClaimStatus.VERIFIED}:
        return "verified"
    if ClaimStatus.USER_ATTESTED in statuses:
        return "user_attested"
    if ClaimStatus.VERIFIED in statuses:
        return "partially_verified"
    return "planned"


def human_summary(result: RecoveryResult) -> str:
    rejection = result.rejection_dict
    guideline_refs = rejection.get("guideline_refs") or []
    mappings = result.ordered_mappings()
    # Prefer the most informative mapping for display: a resolved category
    # beats an ambiguous one, and higher confidence beats lower, but the
    # ordering used for JSON/serialization stability (ordered_mappings) is
    # untouched -- this only affects which one the human summary quotes.
    _confidence_rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    ranked_mappings = sorted(
        mappings, key=lambda m: (m.category.value != "UNKNOWN", _confidence_rank.get(m.confidence.value, 0)),
        reverse=True,
    )
    top_mapping = ranked_mappings[0] if ranked_mappings else None

    lines = [
        "=== APP STORE REJECTION RECOVERY ===",
        "",
        "REJECTION:",
        (f"Guideline(s): {', '.join(guideline_refs)}" if guideline_refs else "Guideline(s): none cited"),
        "",
        "MAPPING:",
        (f"{top_mapping.category.value} / {top_mapping.confidence.value}" if top_mapping else "UNKNOWN / LOW"),
        "",
        "ROOT CAUSE:",
        _root_cause_summary(result.root_causes),
        "",
        "FIX STATUS:",
        _fix_status_summary(result.fix_plans, result.verification_results),
        "",
        "REPLY:",
        result.reply_status,
        "",
        "RESUBMIT_CANDIDATE:",
        result.resubmit_candidate,
        "",
        "RESUBMIT_CANDIDATE=YES does not submit anything. Nothing in this report is sent, applied, or",
        "submitted automatically.",
        "",
        "=== END APP STORE REJECTION RECOVERY ===",
    ]
    return "\n".join(lines)
