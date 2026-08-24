"""Orchestrates the Phase 5 area modules into one Design Review result.

DESIGN_GATE PASS means "no blocking issue and no unresolved rendered/runtime
question was found by the currently implemented rules." It does NOT mean
Apple will approve the app's design, and nothing here should be read,
printed, or serialized in a way that implies otherwise.

Gate logic (exactly, no other cases):
  any BLOCKED               -> BLOCKED
  no BLOCKED, any UNKNOWN   -> CONDITIONAL
  no BLOCKED, no UNKNOWN    -> PASS
RISK alone never forces BLOCKED or CONDITIONAL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..readiness.inspector import ProjectInspector
from . import accessibility, interaction, layout, localization
from .models import DesignFinding, Ruleset, Status, load_ruleset

AREA_ORDER = ("ACCESSIBILITY", "LAYOUT", "LOCALIZATION", "INTERACTION")


@dataclass(frozen=True)
class DesignReviewResult:
    ruleset: Ruleset
    findings: tuple[DesignFinding, ...] | list[DesignFinding] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    def ordered_findings(self) -> tuple[DesignFinding, ...]:
        rank = {name: index for index, name in enumerate(AREA_ORDER)}
        return tuple(sorted(
            self.findings,
            key=lambda item: (rank.get(item.hig_area, len(rank)), item.rule_id),
        ))

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for item in self.findings:
            counts[item.status.value] += 1
        return counts

    @property
    def area_status(self) -> dict[str, str]:
        from ..readiness.models import aggregate_status

        result: dict[str, str] = {}
        for area in AREA_ORDER:
            matches = [item for item in self.findings if item.hig_area == area]
            result[area] = aggregate_status(matches).value if matches else Status.UNKNOWN.value
        return result

    @property
    def gate(self) -> str:
        statuses = {item.status for item in self.findings}
        if Status.BLOCKED in statuses:
            return "BLOCKED"
        if Status.UNKNOWN in statuses:
            return "CONDITIONAL"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset": self.ruleset.to_dict(),
            "design_findings": [item.to_dict() for item in self.ordered_findings()],
            "design_summary": {
                "counts": self.counts,
                "area_status": self.area_status,
                "gate": self.gate,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesignReviewResult":
        return cls(
            ruleset=Ruleset.from_dict(data["ruleset"]),
            findings=tuple(DesignFinding.from_dict(item) for item in data.get("design_findings", [])),
        )


def run_design_review(
    project_path: str | Path, ruleset: Ruleset | None = None, design_evidence: dict | None = None,
) -> DesignReviewResult:
    inspector = ProjectInspector(project_path)
    ruleset = ruleset or load_ruleset()
    findings: list[DesignFinding] = []
    findings.extend(accessibility.evaluate(inspector, ruleset, design_evidence))
    findings.extend(layout.evaluate(inspector, ruleset, design_evidence))
    findings.extend(localization.evaluate(inspector, ruleset, design_evidence))
    findings.extend(interaction.evaluate(inspector, ruleset, design_evidence))
    return DesignReviewResult(ruleset=ruleset, findings=tuple(findings))
