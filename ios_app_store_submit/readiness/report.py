"""Report orchestration and human/JSON rendering."""

from __future__ import annotations

import json
from pathlib import Path

from .gates import inspect_metadata, inspect_reviewability, inspect_technical
from .inspector import ProjectInspector
from .models import GATE_ORDER, GateResult, ReadinessReport, Status


def build_report(project_path: str | Path, *, strict: bool = False) -> ReadinessReport:
    inspector = ProjectInspector(project_path)
    gates = (
        inspect_technical(inspector),
        inspect_metadata(inspector),
        inspect_reviewability(inspector),
    )
    return ReadinessReport(project=str(inspector.root), gates=gates, strict=strict)


def write_json(report: ReadinessReport, output_path: str | Path) -> Path:
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


def report_from_json(path: str | Path) -> ReadinessReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReadinessReport.from_dict(data)


def human_summary(report: ReadinessReport) -> str:
    by_gate = {gate.gate: gate for gate in report.gates}
    counts = report.counts
    lines = [
        "=== IOS APP STORE READINESS SUMMARY ===",
        "",
        f"READY: {report.ready}",
        "",
    ]
    for gate_name in GATE_ORDER:
        status = by_gate.get(gate_name, GateResult(gate_name)).status.value
        lines.append(f"{gate_name:<15} {status}")
    lines.extend([
        "",
        f"PASS        {counts[Status.PASS.value]}",
        f"ADVISORY    {counts[Status.ADVISORY.value]}",
        f"RISK        {counts[Status.RISK.value]}",
        f"BLOCKED     {counts[Status.BLOCKED.value]}",
        f"UNKNOWN     {counts[Status.UNKNOWN.value]}",
        "",
        f"FINAL_GATE: {report.final_gate}",
        "",
        "BLOCKERS:",
    ])
    blockers = [finding for finding in report.ordered_findings() if finding.status is Status.BLOCKED]
    lines.extend(f"- {finding.message}" for finding in blockers)
    if not blockers:
        lines.append("- None")
    lines.extend(["", "=== END SUMMARY ==="])
    return "\n".join(lines)
