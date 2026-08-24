"""Orchestrates the Phase 3 rule modules into one Pre-Review result.

PRE_REVIEW_PASS means "no blocking issue was found by the currently
implemented rules." It does NOT mean "Apple will approve this app," and
nothing here should be read, printed, or serialized in a way that implies
otherwise.

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
from ..readiness.models import ReadinessReport, Status, aggregate_status
from ..readiness.report import build_report
from .models import ReviewFinding, Ruleset
from .registry import load_ruleset
from .rules import metadata as metadata_rules
from .rules import performance as performance_rules
from .rules import privacy as privacy_rules
from .rules import review_access as review_access_rules

CATEGORY_ORDER = ("PERFORMANCE", "METADATA", "REVIEW_ACCESS", "PRIVACY")


@dataclass(frozen=True)
class PreReviewResult:
    ruleset: Ruleset
    findings: tuple[ReviewFinding, ...] | list[ReviewFinding] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    def ordered_findings(self) -> tuple[ReviewFinding, ...]:
        rank = {name: index for index, name in enumerate(CATEGORY_ORDER)}
        return tuple(sorted(
            self.findings,
            key=lambda item: (rank.get(item.category, len(rank)), item.rule_id),
        ))

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for item in self.findings:
            counts[item.status.value] += 1
        return counts

    @property
    def category_status(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for category in CATEGORY_ORDER:
            matches = [item for item in self.findings if item.category == category]
            result[category] = aggregate_status(matches).value if matches else Status.UNKNOWN.value
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
            "review_findings": [item.to_dict() for item in self.ordered_findings()],
            "review_summary": {
                "counts": self.counts,
                "category_status": self.category_status,
                "gate": self.gate,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PreReviewResult":
        return cls(
            ruleset=Ruleset.from_dict(data["ruleset"]),
            findings=tuple(ReviewFinding.from_dict(item) for item in data.get("review_findings", [])),
        )


def run_pre_review(
    project_path: str | Path, readiness_report: ReadinessReport | None = None,
    ruleset: Ruleset | None = None,
) -> PreReviewResult:
    inspector = ProjectInspector(project_path)
    readiness_report = readiness_report or build_report(inspector.root)
    ruleset = ruleset or load_ruleset()
    findings: list[ReviewFinding] = []
    findings.extend(performance_rules.evaluate(inspector, readiness_report, ruleset))
    findings.extend(metadata_rules.evaluate(inspector, readiness_report, ruleset))
    findings.extend(review_access_rules.evaluate(inspector, readiness_report, ruleset))
    findings.extend(privacy_rules.evaluate(inspector, readiness_report, ruleset))
    return PreReviewResult(ruleset=ruleset, findings=tuple(findings))


def human_summary(result: PreReviewResult) -> str:
    counts = result.counts
    cat = result.category_status
    lines = [
        "=== APP STORE PRE-REVIEW ===",
        "",
        "RULESET:",
        result.ruleset.source_name,
        f"Source updated: {result.ruleset.source_last_updated}",
        "",
        f"{'PERFORMANCE / COMPLETENESS':<30}{cat['PERFORMANCE']}",
        f"{'METADATA':<30}{cat['METADATA']}",
        f"{'REVIEW ACCESS':<30}{cat['REVIEW_ACCESS']}",
        f"{'PRIVACY':<30}{cat['PRIVACY']}",
        "",
        f"BLOCKED   {counts[Status.BLOCKED.value]}",
        f"RISK      {counts[Status.RISK.value]}",
        f"UNKNOWN   {counts[Status.UNKNOWN.value]}",
        "",
        "PRE_REVIEW_GATE:",
        result.gate,
        "",
        "This does not mean Apple will approve this app; it means no blocking issue",
        "was found by the currently implemented rules.",
        "",
        "=== END PRE-REVIEW ===",
    ]
    return "\n".join(lines)
