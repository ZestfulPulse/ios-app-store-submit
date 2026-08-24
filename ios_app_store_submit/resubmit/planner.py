"""Read-only Phase 7 plan generation."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .approval import approval_status, load_approval
from .command_builder import build_commands
from .eligibility import evaluate_eligibility
from .models import ApprovalDecision, ResubmitPlan, ResubmitStatus, as_mapping, stable_digest


def load_recovery_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path).expanduser().resolve()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("recovery report must contain a JSON object")
    return data


def _submission_values(report: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, str | None]:
    candidates: list[Mapping[str, Any]] = []
    for key in ("submission", "submission_context", "asc", "discovered_ids"):
        value = report.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    candidates.append(report)
    values: dict[str, str | None] = {}
    aliases = {
        "app_id": ("app_id", "appId", "app"),
        "version": ("version", "version_string", "versionString"),
        "build_id": ("build_id", "buildId", "build"),
        "submission_id": ("submission_id", "submissionId", "id"),
    }
    for field, keys in aliases.items():
        explicit = overrides.get(field)
        found = explicit
        if found is None:
            for candidate in candidates:
                for key in keys:
                    if candidate.get(key) not in (None, ""):
                        found = candidate[key]
                        break
                if found not in (None, ""):
                    break
        values[field] = str(found).strip() if found not in (None, "") else None
    return values


def _reply(report: Mapping[str, Any]) -> tuple[str | None, bool]:
    drafts = report.get("reply_drafts") or ()
    if not drafts:
        return None, False
    draft = drafts[0]
    if not isinstance(draft, Mapping):
        draft = draft.to_dict() if hasattr(draft, "to_dict") else {}
    return draft.get("draft_id"), bool(draft.get("ready_to_send", False))


def plan_resubmission(
    recovery_result: Any, *, project_path: str | Path | None = None, approval: Any = None,
    app_id: str | None = None, version: str | None = None, build_id: str | None = None,
    submission_id: str | None = None,
) -> ResubmitPlan:
    """Build a plan and command preview without executing or writing state."""

    report = as_mapping(recovery_result)
    if report is None:
        report = {}
    report = dict(report)
    eligibility = evaluate_eligibility(report)
    values = _submission_values(
        report, {"app_id": app_id, "version": version, "build_id": build_id, "submission_id": submission_id},
    )
    reply_draft_id, reply_ready = _reply(report)
    report_id = report.get("recovery_report_id") or report.get("rejection_input", {}).get("rejection_id")
    evidence_digest = str(report.get("evidence_digest") or stable_digest(report))
    plan_id = str(report.get("plan_id") or f"resubmit:{report_id or stable_digest(report)[:16]}")

    command_set = build_commands(
        app_id=values["app_id"], version=values["version"], build_id=values["build_id"],
        submission_id=values["submission_id"],
    )
    blockers = set(eligibility.blockers)
    if not reply_ready:
        blockers.add("reply_not_ready")
    for field in ("app_id", "version", "build_id", "submission_id"):
        if values[field] is None:
            blockers.add(f"missing_{field}")
    blockers.update(command_set.blockers)
    required_actions = list(eligibility.conditional_reasons)
    if eligibility.status is ResubmitStatus.NO:
        required_actions.extend(eligibility.blockers)
    if not reply_ready:
        required_actions.append("prepare_ready_to_send_reply")
    if blockers:
        required_actions.extend(sorted(blockers))

    provisional = ResubmitPlan(
        plan_id=plan_id, app_id=values["app_id"], version=values["version"], build_id=values["build_id"],
        submission_id=values["submission_id"], reply_draft_id=reply_draft_id, recovery_report_id=report_id,
        required_actions=tuple(dict.fromkeys(required_actions)), approval_status=ApprovalDecision.PENDING,
        plan_digest="", ready=(eligibility.status is ResubmitStatus.YES and reply_ready and not blockers),
        blockers=tuple(sorted(blockers)), commands=command_set.commands, evidence_digest=evidence_digest,
        selected_command=command_set.selected_command, eligibility=eligibility.status,
    )
    plan = replace(provisional, plan_digest=provisional.computed_digest)
    if approval is None and project_path is not None:
        approval = load_approval(project_path)
    if approval is not None:
        return replace(plan, approval_status=approval_status(plan, approval))
    return plan


def generate_plan(recovery_result: Any, **kwargs: Any) -> ResubmitPlan:
    return plan_resubmission(recovery_result, **kwargs)


def build_resubmit_plan(recovery_result: Any, **kwargs: Any) -> ResubmitPlan:
    return plan_resubmission(recovery_result, **kwargs)


def generate_resubmit_plan(recovery_result: Any, **kwargs: Any) -> ResubmitPlan:
    return plan_resubmission(recovery_result, **kwargs)


__all__ = [
    "build_resubmit_plan", "generate_plan", "generate_resubmit_plan", "load_recovery_report", "plan_resubmission",
]
