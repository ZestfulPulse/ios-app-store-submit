"""Contracts for Phase 2 fix planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FixSafety(str, Enum):
    SAFE = "SAFE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    MANUAL = "MANUAL"
    FORBIDDEN = "FORBIDDEN"

    def __str__(self) -> str:
        return self.value


class FixOperation(str, Enum):
    """The only mutation shapes Phase 2 is allowed to propose. No DELETE, no RENAME."""

    CREATE = "CREATE"
    UPDATE_FORMAT = "UPDATE_FORMAT"
    NORMALIZE_VALUE = "NORMALIZE_VALUE"

    def __str__(self) -> str:
        return self.value


@dataclass
class FixPlan:
    fix_id: str
    finding_id: str
    safety: FixSafety | str
    title: str
    target_path: str
    before: Any
    proposed_after: Any
    reason: str
    verification_rule: str
    applied: bool = False
    verified: bool = False
    operation: FixOperation | str = FixOperation.UPDATE_FORMAT
    rule_id: str | None = None
    evidence: tuple[str, ...] | list[str] = ()
    rollback_possible: bool = True
    verification_result: str | None = None

    def __post_init__(self) -> None:
        self.safety = FixSafety(self.safety)
        self.operation = FixOperation(self.operation)
        if self.rule_id is None:
            self.rule_id = self.finding_id
        self.evidence = tuple(self.evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fix_id": self.fix_id,
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "safety": self.safety.value,
            "title": self.title,
            "target_path": self.target_path,
            "operation": self.operation.value,
            "before": self.before,
            "proposed_after": self.proposed_after,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "verification_rule": self.verification_rule,
            "verified": self.verified,
            "verification_result": self.verification_result,
            "applied": self.applied,
            "rollback_possible": self.rollback_possible,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FixPlan":
        return cls(**{key: value for key, value in data.items()})
