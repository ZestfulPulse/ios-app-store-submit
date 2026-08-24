"""HIG layout checks: safe-area evidence, hardcoded full-screen-like dimensions.

Whether a screen actually clips content or breaks a size class can only be
proven by rendering it; both checks here stay at RISK/UNKNOWN, never BLOCKED.
"""

from __future__ import annotations

from ..readiness.inspector import ProjectInspector
from .inspector import code_files, find_widget_invocations
from .models import Confidence, DesignEvidence, DesignFinding, Ruleset

# Common iPhone logical screen sizes (points). A Container/SizedBox fixed to
# exactly one of these is a heuristic signal of a screen-size assumption,
# never proof of an actual rendering defect.
KNOWN_SCREEN_DIMENSIONS = {
    (320.0, 568.0), (375.0, 667.0), (375.0, 812.0), (390.0, 844.0),
    (414.0, 736.0), (414.0, 896.0), (428.0, 926.0), (430.0, 932.0),
}


def _finding_id(rule_id: str) -> str:
    return f"design.{rule_id.lower().replace('.', '_')}"


def _safe_area(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.LAYOUT.SAFE_AREA")
    files = code_files(inspector)
    scaffold_files = {path for path, _line, _text in inspector.search(r"\bScaffold\s*\(", files)}
    if not scaffold_files:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
            message="No Scaffold was found locally, so there is no local safe-area question to evaluate.",
            evidence=(DesignEvidence(kind="inspection", observed="not found", expected="Scaffold",
                                      parser="regex", confidence=Confidence.MEDIUM),),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
        )

    safe_area_files = {path for path, _line, _text in inspector.search(r"\bSafeArea\s*\(", files)}
    covered = scaffold_files & safe_area_files
    uncovered = scaffold_files - safe_area_files

    if not uncovered:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="PASS", confidence=Confidence.HIGH,
            message="SafeArea usage was found in every file containing a Scaffold.",
            evidence=tuple(
                DesignEvidence(kind="safe_area_usage", source_path=inspector.relative(p), observed="SafeArea( present",
                                expected="SafeArea usage alongside Scaffold", parser="regex", confidence=Confidence.HIGH)
                for p in sorted(covered)
            ),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="UNKNOWN", confidence=Confidence.LOW,
        message=f"{len(uncovered)} file(s) with a Scaffold have no local SafeArea usage; whether the "
                "rendered screen actually clips content cannot be determined from source alone.",
        evidence=tuple(
            DesignEvidence(kind="inspection", source_path=inspector.relative(p), observed="no SafeArea usage found",
                            expected="SafeArea usage or rendered-layout evidence", parser="regex",
                            confidence=Confidence.LOW, runtime_required=True)
            for p in sorted(uncovered)
        ),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
        requested_evidence=("Actual rendered layout evidence showing whether system UI is obscured.",),
    )


def _hardcoded_dimensions(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.LAYOUT.HARDCODED_DIMENSIONS")
    files = code_files(inspector)
    from .inspector import extract_named_number

    matches = []
    for wrapper in ("Container", "SizedBox"):
        for path, line, block, _start, _text in find_widget_invocations(inspector, wrapper, files):
            width = extract_named_number(block, "width")
            height = extract_named_number(block, "height")
            if width is None or height is None:
                continue
            if (width, height) in KNOWN_SCREEN_DIMENSIONS:
                matches.append((path, line, width, height))

    if matches:
        evidence = tuple(
            DesignEvidence(kind="hardcoded_screen_dimension", source_path=inspector.relative(p), line=ln,
                            observed=f"{w:g}x{h:g}", expected="dimensions derived from MediaQuery/LayoutBuilder",
                            parser="regex-balanced-paren", confidence=Confidence.MEDIUM)
            for p, ln, w, h in matches[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(matches)} fixed width+height pair(s) matching a known device screen size; "
                    "this is a heuristic risk signal, not proof of a layout defect.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Derive layout dimensions from MediaQuery/LayoutBuilder instead of a fixed literal.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="No Container/SizedBox fixed to a known device screen size was found.",
        evidence=(DesignEvidence(kind="inspection", observed="not found", expected="fixed screen-size dimension",
                                  parser="regex-balanced-paren", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def evaluate(inspector: ProjectInspector, ruleset: Ruleset, design_evidence: dict | None = None) -> list[DesignFinding]:
    return [
        _safe_area(inspector, ruleset),
        _hardcoded_dimensions(inspector, ruleset),
    ]
