"""Stable data contracts for Phase 3 (Apple Review Guidelines pre-review).

Statuses reuse ``readiness.models.Status``/``Fixability`` so a review finding
means the same PASS/ADVISORY/RISK/BLOCKED/UNKNOWN thing a readiness finding
does; nothing here redefines that vocabulary.

PRE_REVIEW_PASS means "no blocking issue was found by the currently
implemented rules." It does NOT mean "Apple will approve this app."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..readiness.models import Evidence, Fixability, Status
from .provenance import validate_blocked_provenance


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class EvaluationType(_StringEnum):
    DETERMINISTIC = "DETERMINISTIC"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    RISK_HEURISTIC = "RISK_HEURISTIC"


class Confidence(_StringEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def confidence_from_float(value: float) -> Confidence:
    if value >= 0.85:
        return Confidence.HIGH
    if value >= 0.65:
        return Confidence.MEDIUM
    return Confidence.LOW


@dataclass(frozen=True)
class Rule:
    rule_id: str
    apple_guideline: str
    category: str
    title: str
    description: str
    severity_default: Status | str
    evaluation_type: EvaluationType | str
    required_evidence: tuple[str, ...] | list[str]
    fixability: Fixability | str
    source_url: str
    source_last_updated: str
    confidence_policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity_default", Status(self.severity_default))
        object.__setattr__(self, "evaluation_type", EvaluationType(self.evaluation_type))
        object.__setattr__(self, "fixability", Fixability(self.fixability))
        object.__setattr__(self, "required_evidence", tuple(self.required_evidence))
        if self.evaluation_type is EvaluationType.RISK_HEURISTIC and self.severity_default is Status.BLOCKED:
            raise ValueError(f"{self.rule_id}: a RISK_HEURISTIC rule may not have severity_default=BLOCKED")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "apple_guideline": self.apple_guideline,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "severity_default": self.severity_default.value,
            "evaluation_type": self.evaluation_type.value,
            "required_evidence": list(self.required_evidence),
            "fixability": self.fixability.value,
            "source_url": self.source_url,
            "source_last_updated": self.source_last_updated,
            "confidence_policy": self.confidence_policy,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Rule":
        return cls(**{key: data[key] for key in (
            "rule_id", "apple_guideline", "category", "title", "description", "severity_default",
            "evaluation_type", "required_evidence", "fixability", "source_url", "source_last_updated",
            "confidence_policy",
        )})


@dataclass(frozen=True)
class Ruleset:
    ruleset_id: str
    source_name: str
    source_url: str
    source_last_updated: str
    snapshot_date: str
    source_language: str
    schema_version: str
    rules: tuple[Rule, ...] | list[Rule] = field(default_factory=tuple)
    future_sources: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(self, "future_sources", tuple(self.future_sources))

    def rule(self, rule_id: str) -> Rule:
        for candidate in self.rules:
            if candidate.rule_id == rule_id:
                return candidate
        raise KeyError(f"unknown rule_id: {rule_id}")

    def rules_by_category(self, category: str) -> tuple[Rule, ...]:
        return tuple(item for item in self.rules if item.category == category)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_last_updated": self.source_last_updated,
            "snapshot_date": self.snapshot_date,
            "source_language": self.source_language,
            "schema_version": self.schema_version,
            "rules": [item.to_dict() for item in self.rules],
            "future_sources": [dict(item) for item in self.future_sources],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Ruleset":
        return cls(
            ruleset_id=data["ruleset_id"], source_name=data["source_name"], source_url=data["source_url"],
            source_last_updated=data["source_last_updated"], snapshot_date=data["snapshot_date"],
            source_language=data["source_language"], schema_version=data["schema_version"],
            rules=tuple(Rule.from_dict(item) for item in data.get("rules", [])),
            future_sources=tuple(data.get("future_sources", [])),
        )


@dataclass(frozen=True)
class ReviewFinding:
    finding_id: str
    rule_id: str
    apple_guideline: str
    category: str
    status: Status | str
    confidence: Confidence | str
    message: str
    evidence: tuple[Evidence, ...] | list[Evidence] = field(default_factory=tuple)
    source_url: str = ""
    source_last_updated: str = ""
    ruleset_id: str = ""
    fixability: Fixability | str = Fixability.NONE
    blocking: bool = False
    suggested_fix: str | None = None
    requested_evidence: tuple[str, ...] | list[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        status = Status(self.status)
        confidence = Confidence(self.confidence)
        fixability = Fixability(self.fixability)
        evidence = tuple(
            item if isinstance(item, Evidence) else Evidence.from_dict(item)
            for item in self.evidence
        )
        validate_blocked_provenance(
            status=status.value, evidence=evidence, rule_id=self.rule_id,
            apple_guideline=self.apple_guideline, source_url=self.source_url,
            source_last_updated=self.source_last_updated, ruleset_id=self.ruleset_id,
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "fixability", fixability)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "requested_evidence", tuple(self.requested_evidence))
        if status is Status.BLOCKED and not self.blocking:
            object.__setattr__(self, "blocking", True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "apple_guideline": self.apple_guideline,
            "category": self.category,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "message": self.message,
            "evidence": [item.to_dict() for item in self.evidence],
            "source_url": self.source_url,
            "source_last_updated": self.source_last_updated,
            "ruleset_id": self.ruleset_id,
            "fixability": self.fixability.value,
            "blocking": self.blocking,
            "suggested_fix": self.suggested_fix,
            "requested_evidence": list(self.requested_evidence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewFinding":
        return cls(
            finding_id=data["finding_id"], rule_id=data["rule_id"], apple_guideline=data["apple_guideline"],
            category=data["category"], status=data["status"], confidence=data["confidence"],
            message=data["message"], evidence=tuple(Evidence.from_dict(item) for item in data.get("evidence", [])),
            source_url=data.get("source_url", ""), source_last_updated=data.get("source_last_updated", ""),
            ruleset_id=data.get("ruleset_id", ""), fixability=data.get("fixability", Fixability.NONE),
            blocking=data.get("blocking", False), suggested_fix=data.get("suggested_fix"),
            requested_evidence=tuple(data.get("requested_evidence", [])),
        )
