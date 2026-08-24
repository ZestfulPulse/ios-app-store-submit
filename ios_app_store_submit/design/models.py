"""Stable data contracts for Phase 5 (HIG / Design Review).

Statuses reuse ``readiness.models.Status``/``Fixability`` and check-type /
confidence reuse ``review.models.EvaluationType``/``Confidence`` so a design
finding means the same PASS/ADVISORY/RISK/BLOCKED/UNKNOWN thing every other
phase's finding does; nothing here redefines that vocabulary.

Invariants enforced at construction time (never left to call-site
discipline):

1. A RISK_HEURISTIC rule may not default to BLOCKED (mirrors Phase 3).
2. A DesignFinding may not be BLOCKED with check_type RISK_HEURISTIC --
   heuristic-only evidence can never BLOCK, no matter what a call site
   passes as status_override.
3. A BLOCKED DesignFinding requires evidence and full provenance
   (rule_id, source_url, ruleset_id).

DESIGN_GATE PASS means "no blocking issue and no unresolved rendered/runtime
question was found by the currently implemented rules." It is a risk
assessment, not an Apple approval guarantee.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..readiness.models import Fixability, Status
from ..review.models import Confidence, EvaluationType, confidence_from_float

__all__ = [
    "Confidence", "EvaluationType", "confidence_from_float", "Fixability", "Status",
    "DesignEvidence", "DesignFinding", "Rule", "Ruleset", "load_ruleset",
]

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "apple_rules" / "hig_rules.json"


@dataclass(frozen=True)
class DesignEvidence:
    kind: str
    source_path: str | None = None
    line: int | None = None
    symbol: str | None = None
    observed: Any = None
    expected: Any = None
    parser: str | None = None
    confidence: Confidence | str = Confidence.LOW
    runtime_required: bool = False
    screenshot_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", Confidence(self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_path": self.source_path,
            "line": self.line,
            "symbol": self.symbol,
            "observed": self.observed,
            "expected": self.expected,
            "parser": self.parser,
            "confidence": self.confidence.value,
            "runtime_required": self.runtime_required,
            "screenshot_required": self.screenshot_required,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DesignEvidence":
        return cls(
            kind=data["kind"], source_path=data.get("source_path"), line=data.get("line"),
            symbol=data.get("symbol"), observed=data.get("observed"), expected=data.get("expected"),
            parser=data.get("parser"), confidence=data.get("confidence", Confidence.LOW),
            runtime_required=data.get("runtime_required", False),
            screenshot_required=data.get("screenshot_required", False),
        )


@dataclass(frozen=True)
class Rule:
    rule_id: str
    hig_area: str
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
            "hig_area": self.hig_area,
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
            "rule_id", "hig_area", "title", "description", "severity_default",
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

    def rules_by_area(self, hig_area: str) -> tuple[Rule, ...]:
        return tuple(item for item in self.rules if item.hig_area == hig_area)

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


def load_ruleset(path: str | Path | None = None) -> Ruleset:
    target = Path(path).expanduser() if path is not None else DEFAULT_REGISTRY_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    return Ruleset.from_dict(data)


def _validate_blocked(
    *, status: Status, evaluation_type: EvaluationType, evidence: tuple[DesignEvidence, ...],
    rule_id: str | None, source_url: str | None, ruleset_id: str | None,
) -> None:
    if status is not Status.BLOCKED:
        return
    if evaluation_type is EvaluationType.RISK_HEURISTIC:
        raise ValueError(f"{rule_id}: a heuristic-only finding may not BLOCK")
    missing = [name for name, value in (
        ("evidence", evidence), ("rule_id", rule_id), ("source_url", source_url), ("ruleset_id", ruleset_id),
    ) if not value]
    if missing:
        raise ValueError(f"BLOCKED design finding missing required evidence/provenance: {', '.join(missing)}")


@dataclass(frozen=True)
class DesignFinding:
    finding_id: str
    rule_id: str
    hig_area: str
    title: str
    status: Status | str
    confidence: Confidence | str
    message: str
    evidence: tuple[DesignEvidence, ...] | list[DesignEvidence] = field(default_factory=tuple)
    source_url: str = ""
    ruleset_id: str = ""
    check_type: EvaluationType | str = EvaluationType.RISK_HEURISTIC
    fixability: Fixability | str = Fixability.NONE
    blocking: bool = False
    requested_evidence: tuple[str, ...] | list[str] = field(default_factory=tuple)
    suggested_fix: str | None = None

    def __post_init__(self) -> None:
        status = Status(self.status)
        confidence = Confidence(self.confidence)
        fixability = Fixability(self.fixability)
        check_type = EvaluationType(self.check_type)
        evidence = tuple(
            item if isinstance(item, DesignEvidence) else DesignEvidence.from_dict(item)
            for item in self.evidence
        )
        _validate_blocked(
            status=status, evaluation_type=check_type, evidence=evidence, rule_id=self.rule_id,
            source_url=self.source_url, ruleset_id=self.ruleset_id,
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "fixability", fixability)
        object.__setattr__(self, "check_type", check_type)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "requested_evidence", tuple(self.requested_evidence))
        if status is Status.BLOCKED and not self.blocking:
            object.__setattr__(self, "blocking", True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "hig_area": self.hig_area,
            "title": self.title,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "message": self.message,
            "evidence": [item.to_dict() for item in self.evidence],
            "source_url": self.source_url,
            "ruleset_id": self.ruleset_id,
            "check_type": self.check_type.value,
            "fixability": self.fixability.value,
            "blocking": self.blocking,
            "requested_evidence": list(self.requested_evidence),
            "suggested_fix": self.suggested_fix,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DesignFinding":
        return cls(
            finding_id=data["finding_id"], rule_id=data["rule_id"], hig_area=data["hig_area"],
            title=data["title"], status=data["status"], confidence=data["confidence"], message=data["message"],
            evidence=tuple(DesignEvidence.from_dict(item) for item in data.get("evidence", [])),
            source_url=data.get("source_url", ""), ruleset_id=data.get("ruleset_id", ""),
            check_type=data.get("check_type", EvaluationType.RISK_HEURISTIC),
            fixability=data.get("fixability", Fixability.NONE), blocking=data.get("blocking", False),
            requested_evidence=tuple(data.get("requested_evidence", [])),
            suggested_fix=data.get("suggested_fix"),
        )
