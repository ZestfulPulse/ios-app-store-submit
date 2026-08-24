"""Stable data contracts used by readiness checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Status(_StringEnum):
    PASS = "PASS"
    ADVISORY = "ADVISORY"
    RISK = "RISK"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class Fixability(_StringEnum):
    AUTO = "AUTO"
    APPROVAL = "APPROVAL"
    MANUAL = "MANUAL"
    UNFIXABLE = "UNFIXABLE"
    NONE = "NONE"


@dataclass(frozen=True)
class Evidence:
    kind: str
    path: str | None = None
    key: str | None = None
    observed: Any = None
    expected: Any = None
    source: str | None = None
    line: int | None = None
    command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "key": self.key,
            "observed": self.observed,
            "expected": self.expected,
            "source": self.source,
            "line": self.line,
            "command": self.command,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Evidence":
        return cls(**{field: data.get(field) for field in (
            "kind", "path", "key", "observed", "expected", "source", "line", "command"
        )})


@dataclass(frozen=True)
class Finding:
    finding_id: str
    gate: str
    rule_id: str
    title: str
    status: Status | str
    message: str
    evidence: tuple[Evidence, ...] | list[Evidence] = field(default_factory=tuple)
    source_path: str | None = None
    confidence: float = 1.0
    fixability: Fixability | str = Fixability.NONE
    suggested_fix: str | None = None
    blocking: bool = False

    def __post_init__(self) -> None:
        status = Status(self.status)
        fixability = Fixability(self.fixability)
        evidence = tuple(
            item if isinstance(item, Evidence) else Evidence.from_dict(item)
            for item in self.evidence
        )
        if status is Status.BLOCKED and not evidence:
            raise ValueError("BLOCKED findings require evidence")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "fixability", fixability)
        object.__setattr__(self, "evidence", evidence)
        if status is Status.BLOCKED and not self.blocking:
            object.__setattr__(self, "blocking", True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "gate": self.gate,
            "rule_id": self.rule_id,
            "title": self.title,
            "status": self.status.value,
            "message": self.message,
            "evidence": [item.to_dict() for item in self.evidence],
            "source_path": self.source_path,
            "confidence": self.confidence,
            "fixability": self.fixability.value,
            "suggested_fix": self.suggested_fix,
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Finding":
        return cls(
            finding_id=data["finding_id"],
            gate=data["gate"],
            rule_id=data["rule_id"],
            title=data["title"],
            status=data["status"],
            message=data["message"],
            evidence=tuple(Evidence.from_dict(item) for item in data.get("evidence", [])),
            source_path=data.get("source_path"),
            confidence=data.get("confidence", 1.0),
            fixability=data.get("fixability", Fixability.NONE),
            suggested_fix=data.get("suggested_fix"),
            blocking=data.get("blocking", False),
        )


@dataclass(frozen=True)
class GateResult:
    gate: str
    findings: tuple[Finding, ...] | list[Finding] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    @property
    def status(self) -> Status:
        return aggregate_status(self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status.value,
            "findings": [item.to_dict() for item in self.findings],
        }


GATE_ORDER = ("TECHNICAL", "METADATA", "REVIEWABILITY")
STATUS_ORDER = (Status.BLOCKED, Status.UNKNOWN, Status.RISK, Status.ADVISORY, Status.PASS)


def aggregate_status(findings: Iterable[Finding]) -> Status:
    statuses = {item.status for item in findings}
    for status in STATUS_ORDER:
        if status in statuses:
            return status
    return Status.PASS


@dataclass(frozen=True)
class ReadinessReport:
    project: str
    gates: tuple[GateResult, ...] | list[GateResult] = field(default_factory=tuple)
    strict: bool = False

    def __post_init__(self) -> None:
        gates = tuple(self.gates)
        object.__setattr__(self, "gates", gates)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(item for gate in self.gates for item in gate.findings)

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for finding in self.findings:
            counts[finding.status.value] += 1
        return counts

    @property
    def ready(self) -> str:
        statuses = {item.status for item in self.findings}
        if Status.BLOCKED in statuses or (self.strict and Status.UNKNOWN in statuses):
            return "NO"
        if Status.UNKNOWN in statuses:
            return "CONDITIONAL"
        return "YES"

    @property
    def final_gate(self) -> str:
        return self.ready

    def ordered_findings(self) -> tuple[Finding, ...]:
        gate_rank = {name: index for index, name in enumerate(GATE_ORDER)}
        return tuple(sorted(
            self.findings,
            key=lambda item: (gate_rank.get(item.gate, len(gate_rank)), item.finding_id),
        ))

    def to_dict(self) -> dict[str, Any]:
        ordered_gates = sorted(
            self.gates,
            key=lambda item: (GATE_ORDER.index(item.gate) if item.gate in GATE_ORDER else len(GATE_ORDER), item.gate),
        )
        return {
            "project": self.project,
            "strict": self.strict,
            "ready": self.ready,
            "final_gate": self.final_gate,
            "counts": self.counts,
            "gates": [gate.to_dict() for gate in ordered_gates],
            "findings": [finding.to_dict() for finding in self.ordered_findings()],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReadinessReport":
        gates = tuple(
            GateResult(
                gate=item["gate"],
                findings=tuple(Finding.from_dict(finding) for finding in item.get("findings", [])),
            )
            for item in data.get("gates", [])
        )
        return cls(project=data["project"], gates=gates, strict=data.get("strict", False))
