"""Human-readable rendering for a Phase 5 DesignReviewResult, plus the
optional ``--design-evidence`` JSON loader.

Loading a supplied evidence file is read-only: Phase 5 never launches a
simulator or device, never captures a screenshot, and never performs OCR.
The file is architecture for a *future* phase that ingests real rendered-UI
measurements; nothing here fabricates such evidence itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from .evaluator import DesignReviewResult
from .models import Status


def load_design_evidence(path: str | Path) -> dict:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("--design-evidence file must contain a JSON object")
    return data


def human_summary(result: DesignReviewResult) -> str:
    counts = result.counts
    area = result.area_status
    lines = [
        "=== HIG / DESIGN REVIEW ===",
        "",
        f"{'ACCESSIBILITY':<18}{area['ACCESSIBILITY']}",
        f"{'LAYOUT':<18}{area['LAYOUT']}",
        f"{'LOCALIZATION':<18}{area['LOCALIZATION']}",
        f"{'INTERACTION':<18}{area['INTERACTION']}",
        "",
        f"DETERMINISTIC FINDINGS  {counts[Status.BLOCKED.value]}",
        f"RISKS                   {counts[Status.RISK.value]}",
        f"UNKNOWN                 {counts[Status.UNKNOWN.value]}",
        "",
        "DESIGN_GATE:",
        result.gate,
        "",
        "Design review is a risk assessment, not an Apple approval guarantee.",
        "",
        "=== END HIG / DESIGN REVIEW ===",
    ]
    return "\n".join(lines)
