"""Human and JSON reporting for the closed-loop review cycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .approval import approval_status
from .models import (
    ApprovalDecision, ApprovalRecord, EligibilityResult, ExecutionResult, ExecutionStatus,
    ResubmitPlan, ResubmitStatus,
)


@dataclass(frozen=True)
class ClosedLoopReport:
    eligibility: EligibilityResult
    plan: ResubmitPlan
    approval: ApprovalDecision | str = ApprovalDecision.PENDING
    execution: ExecutionResult = field(default_factory=ExecutionResult)

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval", ApprovalDecision(self.approval))
        if not isinstance(self.execution, ExecutionResult):
            object.__setattr__(self, "execution", ExecutionResult.from_dict(self.execution))

    @property
    def recovery_gate(self) -> str:
        return self.eligibility.status.value

    @property
    def plan_status(self) -> str:
        if self.eligibility.status is ResubmitStatus.CONDITIONAL and not self.plan.blockers:
            return "CONDITIONAL"
        return "READY" if self.plan.ready else "BLOCKED"

    @property
    def post_submit_state(self) -> str:
        return self.execution.post_submit.state or "UNKNOWN"

    @property
    def final(self) -> str:
        if self.execution.status is ExecutionStatus.SUCCESS and self.execution.post_submit.verified:
            return "RESUBMITTED_VERIFIED"
        if self.plan_status == "BLOCKED":
            return "BLOCKED"
        return "NEEDS_USER_ACTION"

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_gate": self.recovery_gate,
            "eligibility": self.eligibility.to_dict(),
            "plan": self.plan.to_dict(),
            "plan_status": self.plan_status,
            "approval": self.approval.value,
            "execution": self.execution.to_dict(),
            "post_submit_state": self.post_submit_state,
            "final": self.final,
        }


def build_report(
    eligibility: EligibilityResult, plan: ResubmitPlan, approval: ApprovalRecord | None = None,
    execution: ExecutionResult | None = None,
) -> ClosedLoopReport:
    status = approval_status(plan, approval)
    return ClosedLoopReport(eligibility, plan, status, execution or ExecutionResult())


def report_from_dict(data: Mapping[str, Any]) -> ClosedLoopReport:
    return ClosedLoopReport(
        eligibility=EligibilityResult.from_dict(data.get("eligibility", {})),
        plan=ResubmitPlan.from_dict(data.get("plan", {})), approval=data.get("approval", "PENDING"),
        execution=ExecutionResult.from_dict(data.get("execution", {})),
    )


def human_summary(report: ClosedLoopReport) -> str:
    return "\n".join([
        "=== CLOSED-LOOP RESUBMISSION ===",
        "",
        "RECOVERY_GATE:", report.recovery_gate,
        "",
        "PLAN:", report.plan_status,
        "",
        "APPROVAL:", report.approval.value,
        "",
        "EXECUTION:", report.execution.status.value,
        "",
        "POST_SUBMIT_STATE:", report.post_submit_state,
        "",
        "FINAL:", report.final,
        "",
        "Nothing should be submitted unless explicit approval is recorded.",
        "=== END CLOSED-LOOP RESUBMISSION ===",
    ])


def json_report(report: ClosedLoopReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def render_human_summary(report: ClosedLoopReport) -> str:
    return human_summary(report)


__all__ = [
    "ClosedLoopReport", "build_report", "human_summary", "json_report", "render_human_summary", "report_from_dict",
]
