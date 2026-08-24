"""Stable data contracts for Phase 7.

The digest is intentionally calculated from only submission-relevant,
non-secret data.  Approval is a binding over that digest, not over a command
history or an earlier release.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ResubmitStatus(_StringEnum):
    YES = "YES"
    NO = "NO"
    CONDITIONAL = "CONDITIONAL"


class ApprovalDecision(_StringEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"
    STALE = "STALE"


class ExecutionStatus(_StringEnum):
    NOT_RUN = "NOT_RUN"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def stable_digest(value: Any) -> str:
    """Return a deterministic SHA-256 digest for JSON-compatible data."""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _tuple(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


@dataclass(frozen=True)
class EligibilityResult:
    status: ResubmitStatus | str
    blockers: tuple[str, ...] | list[str] = field(default_factory=tuple)
    conditional_reasons: tuple[str, ...] | list[str] = field(default_factory=tuple)
    recovery_report_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResubmitStatus(self.status))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(self, "conditional_reasons", tuple(sorted(set(self.conditional_reasons))))

    @property
    def eligibility(self) -> ResubmitStatus:
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "blockers": list(self.blockers),
            "conditional_reasons": list(self.conditional_reasons),
            "recovery_report_id": self.recovery_report_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EligibilityResult":
        return cls(
            status=data.get("status", data.get("eligibility", "NO")),
            blockers=tuple(data.get("blockers", ())),
            conditional_reasons=tuple(data.get("conditional_reasons", ())),
            recovery_report_id=data.get("recovery_report_id"),
        )


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    scope: str
    decision: ApprovalDecision | str
    approved_at: str | None = None
    approved_by: str | None = None
    evidence_digest: str | None = None
    planned_submission_digest: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", ApprovalDecision(self.decision))

    def status_for(self, plan: "ResubmitPlan") -> ApprovalDecision:
        if self.decision is not ApprovalDecision.APPROVED:
            return self.decision
        if self.planned_submission_digest != plan.plan_digest:
            return ApprovalDecision.STALE
        if self.evidence_digest and plan.evidence_digest and self.evidence_digest != plan.evidence_digest:
            return ApprovalDecision.STALE
        if not self.approved_at or not self.approved_by:
            return ApprovalDecision.STALE
        return ApprovalDecision.APPROVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "scope": self.scope,
            "decision": self.decision.value,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "evidence_digest": self.evidence_digest,
            "planned_submission_digest": self.planned_submission_digest,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ApprovalRecord":
        return cls(
            approval_id=str(data.get("approval_id", "")), scope=str(data.get("scope", "resubmit")),
            decision=data.get("decision", "PENDING"), approved_at=data.get("approved_at"),
            approved_by=data.get("approved_by"), evidence_digest=data.get("evidence_digest"),
            planned_submission_digest=data.get("planned_submission_digest"), notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class CommandSet:
    """Commands are previews only; constructing this object never runs them."""

    commands: tuple[str, ...] | list[str] = field(default_factory=tuple)
    selected_command: str | None = None
    preview: str = ""
    blockers: tuple[str, ...] | list[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "commands", tuple(self.commands))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        if self.selected_command and self.selected_command not in self.commands:
            raise ValueError("selected_command must be one of commands")

    @property
    def ready(self) -> bool:
        return bool(self.selected_command) and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "commands": list(self.commands),
            "selected_command": self.selected_command,
            "preview": self.preview,
            "blockers": list(self.blockers),
            "ready": self.ready,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandSet":
        return cls(
            commands=tuple(data.get("commands", ())), selected_command=data.get("selected_command"),
            preview=str(data.get("preview", "")), blockers=tuple(data.get("blockers", ())),
        )


@dataclass(frozen=True)
class ResubmitPlan:
    plan_id: str
    app_id: str | None = None
    version: str | None = None
    build_id: str | None = None
    submission_id: str | None = None
    reply_draft_id: str | None = None
    recovery_report_id: str | None = None
    required_actions: tuple[str, ...] | list[str] = field(default_factory=tuple)
    approval_status: ApprovalDecision | str = ApprovalDecision.PENDING
    plan_digest: str = ""
    ready: bool = False
    blockers: tuple[str, ...] | list[str] = field(default_factory=tuple)
    commands: tuple[str, ...] | list[str] = field(default_factory=tuple)
    evidence_digest: str = ""
    selected_command: str | None = None
    eligibility: ResubmitStatus | str = ResubmitStatus.NO

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_status", ApprovalDecision(self.approval_status))
        object.__setattr__(self, "eligibility", ResubmitStatus(self.eligibility))
        object.__setattr__(self, "required_actions", tuple(self.required_actions))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(self, "commands", tuple(self.commands))
        if self.selected_command and self.selected_command not in self.commands:
            raise ValueError("selected_command must be one of commands")
        if not self.plan_digest:
            object.__setattr__(self, "plan_digest", self.computed_digest)

    def digest_payload(self) -> dict[str, Any]:
        """The immutable submission intent bound by an approval record."""

        return {
            "plan_id": self.plan_id,
            "app_id": self.app_id,
            "version": self.version,
            "build_id": self.build_id,
            "submission_id": self.submission_id,
            "reply_draft_id": self.reply_draft_id,
            "recovery_report_id": self.recovery_report_id,
            "required_actions": list(self.required_actions),
            "blockers": list(self.blockers),
            "commands": list(self.commands),
            "selected_command": self.selected_command,
            "evidence_digest": self.evidence_digest,
            "eligibility": self.eligibility.value,
        }

    @property
    def computed_digest(self) -> str:
        return stable_digest(self.digest_payload())

    @property
    def digest_valid(self) -> bool:
        return bool(self.plan_digest) and self.plan_digest == self.computed_digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "app_id": self.app_id,
            "version": self.version,
            "build_id": self.build_id,
            "submission_id": self.submission_id,
            "reply_draft_id": self.reply_draft_id,
            "recovery_report_id": self.recovery_report_id,
            "required_actions": list(self.required_actions),
            "approval_status": self.approval_status.value,
            "plan_digest": self.plan_digest,
            "ready": self.ready,
            "blockers": list(self.blockers),
            "commands": list(self.commands),
            "selected_command": self.selected_command,
            "evidence_digest": self.evidence_digest,
            "eligibility": self.eligibility.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResubmitPlan":
        return cls(
            plan_id=str(data.get("plan_id", "")), app_id=data.get("app_id"), version=data.get("version"),
            build_id=data.get("build_id"), submission_id=data.get("submission_id"),
            reply_draft_id=data.get("reply_draft_id"), recovery_report_id=data.get("recovery_report_id"),
            required_actions=tuple(data.get("required_actions", ())),
            approval_status=data.get("approval_status", "PENDING"), plan_digest=str(data.get("plan_digest", "")),
            ready=bool(data.get("ready", False)), blockers=tuple(data.get("blockers", ())),
            commands=tuple(data.get("commands", ())), selected_command=data.get("selected_command"),
            evidence_digest=str(data.get("evidence_digest", "")), eligibility=data.get("eligibility", "NO"),
        )


@dataclass(frozen=True)
class PostSubmitVerification:
    state: str | None
    verified: bool
    evidence: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "verified": self.verified, "evidence": self.evidence, "message": self.message}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PostSubmitVerification":
        return cls(data.get("state"), bool(data.get("verified", False)), str(data.get("evidence", "")), str(data.get("message", "")))


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus | str = ExecutionStatus.NOT_RUN
    command: str | None = None
    returncode: int | None = None
    post_submit: PostSubmitVerification = field(default_factory=lambda: PostSubmitVerification(None, False))
    message: str = ""
    retry_attempted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ExecutionStatus(self.status))
        if not isinstance(self.post_submit, PostSubmitVerification):
            object.__setattr__(self, "post_submit", PostSubmitVerification.from_dict(self.post_submit))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value, "command": self.command, "returncode": self.returncode,
            "post_submit": self.post_submit.to_dict(), "message": self.message,
            "retry_attempted": self.retry_attempted,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionResult":
        return cls(
            status=data.get("status", "NOT_RUN"), command=data.get("command"), returncode=data.get("returncode"),
            post_submit=PostSubmitVerification.from_dict(data.get("post_submit", {})),
            message=str(data.get("message", "")), retry_attempted=bool(data.get("retry_attempted", False)),
        )


def as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return result if isinstance(result, Mapping) else None
    return None


__all__ = [
    "ApprovalDecision", "ApprovalRecord", "CommandSet", "EligibilityResult", "ExecutionResult",
    "ExecutionStatus", "PostSubmitVerification", "ResubmitPlan", "ResubmitStatus", "stable_digest",
]
