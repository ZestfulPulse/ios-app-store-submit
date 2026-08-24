"""Explicit local approval gate for resubmission."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ApprovalDecision, ApprovalRecord, ResubmitPlan


def approval_path(project_path: str | Path) -> Path:
    return Path(project_path).expanduser().resolve() / ".asc" / "resubmit" / "approval.json"


def load_approval(project_path: str | Path) -> ApprovalRecord | None:
    path = approval_path(project_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return ApprovalRecord.from_dict(data) if isinstance(data, dict) else None


def approval_status(plan: ResubmitPlan, approval: ApprovalRecord | None) -> ApprovalDecision:
    if approval is None:
        return ApprovalDecision.PENDING
    if not plan.digest_valid:
        return ApprovalDecision.STALE if approval.decision is ApprovalDecision.APPROVED else approval.decision
    return approval.status_for(plan)


def create_approval(
    plan: ResubmitPlan, *, approval_digest: str, approved_by: str = "explicit-user",
    scope: str | None = None, notes: str = "",
) -> ApprovalRecord:
    """Create an approval record without executing or contacting ASC."""

    if not approval_digest or approval_digest != plan.plan_digest or not plan.digest_valid:
        raise ValueError("approval digest must exactly match the current valid plan digest")
    if not approved_by.strip():
        raise ValueError("approved_by is required for explicit approval")
    return ApprovalRecord(
        approval_id=f"approval:{plan.plan_digest[:16]}", scope=scope or f"resubmit:{plan.plan_id}",
        decision=ApprovalDecision.APPROVED, approved_at=datetime.now(timezone.utc).isoformat(),
        approved_by=approved_by, evidence_digest=plan.evidence_digest or None,
        planned_submission_digest=plan.plan_digest, notes=notes,
    )


def write_approval(project_path: str | Path, record: ApprovalRecord) -> Path:
    """Persist only the local, non-secret approval artifact."""

    path = approval_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_approval(plan: ResubmitPlan, approval: ApprovalRecord | None, *, approval_digest: str | None = None) -> tuple[bool, tuple[str, ...]]:
    """Return whether approval is executable and why it is not, if not."""

    blockers: list[str] = []
    if approval is None:
        blockers.append("missing_approval")
        return False, tuple(blockers)
    if approval_digest and approval_digest != plan.plan_digest:
        blockers.append("approval_digest_mismatch")
    if not plan.digest_valid:
        blockers.append("plan_digest_invalid")
    status = approval_status(plan, approval)
    if status is ApprovalDecision.STALE:
        blockers.append("stale_approval")
    elif status is not ApprovalDecision.APPROVED:
        blockers.append(f"approval_{status.value.lower()}")
    if approval.planned_submission_digest != plan.plan_digest:
        blockers.append("approval_not_bound_to_plan")
    return not blockers, tuple(sorted(set(blockers)))


def is_approval_valid(plan: ResubmitPlan, approval: ApprovalRecord | None, *, approval_digest: str | None = None) -> bool:
    return validate_approval(plan, approval, approval_digest=approval_digest)[0]


def record_approval(project_path: str | Path, plan: ResubmitPlan, *, approval_digest: str,
                    approved_by: str = "explicit-user", scope: str | None = None, notes: str = "") -> ApprovalRecord:
    record = create_approval(
        plan, approval_digest=approval_digest, approved_by=approved_by, scope=scope, notes=notes,
    )
    write_approval(project_path, record)
    return record


__all__ = [
    "approval_path", "approval_status", "create_approval", "is_approval_valid", "load_approval",
    "record_approval", "validate_approval", "write_approval",
]
