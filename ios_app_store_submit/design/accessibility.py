"""HIG accessibility checks: touch-target size, icon-only labeling, Dynamic Type.

Deterministic where an explicit fixed-size literal is directly parsed;
UNKNOWN when a control's rendered size cannot be established statically;
never BLOCKED from a heuristic signal alone (Dynamic Type stays RISK).
"""

from __future__ import annotations

import re

from ..readiness.inspector import ProjectInspector
from .inspector import (
    code_files, extract_named_number, find_widget_invocations, has_named_arg,
)
from .models import Confidence, DesignEvidence, DesignFinding, EvaluationType, Ruleset

INTERACTIVE_WIDGETS = ("GestureDetector", "InkWell", "IconButton")
SIZE_WRAPPERS = ("SizedBox", "Container")
MIN_TOUCH_TARGET = 44.0

_KEY_PATTERN = re.compile(r"\bKey\(\s*['\"]([^'\"]+)['\"]")
_FONT_SIZE_PATTERN = re.compile(r"\bfontSize\s*:\s*(\d+(?:\.\d+)?)")
_TEXT_SCALE_PATTERN = re.compile(r"\btextScaleFactor\b|\btextScaler\b|\bMediaQuery\.textScalerOf\b")


def _finding_id(rule_id: str) -> str:
    return f"design.{rule_id.lower().replace('.', '_')}"


def _rendered_size_for(block: str, design_evidence: dict | None):
    if not design_evidence:
        return None
    match = _KEY_PATTERN.search(block)
    if not match:
        return None
    entry = (design_evidence.get("rendered_sizes") or {}).get(match.group(1))
    if not isinstance(entry, dict) or "width" not in entry or "height" not in entry:
        return None
    return entry["width"], entry["height"], match.group(1)


def _touch_target_size(inspector: ProjectInspector, ruleset: Ruleset, design_evidence: dict | None) -> DesignFinding:
    rule = ruleset.rule("DESIGN.ACCESSIBILITY.TOUCH_TARGET_SIZE")
    files = code_files(inspector)
    any_interactive = any(
        inspector.search(rf"\b{name}\s*\(", files) for name in INTERACTIVE_WIDGETS
    )
    if not any_interactive:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
            message="No interactive controls (GestureDetector/InkWell/IconButton) were found locally.",
            evidence=(DesignEvidence(kind="inspection", observed="not found",
                                      expected="interactive control", parser="regex", confidence=Confidence.MEDIUM),),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
        )

    undersized = []
    unresolved = False
    wrapping_found = False
    for wrapper in SIZE_WRAPPERS:
        for path, line, block, _start, _text in find_widget_invocations(inspector, wrapper, files):
            if not any(name in block for name in INTERACTIVE_WIDGETS):
                continue
            wrapping_found = True
            width = extract_named_number(block, "width")
            height = extract_named_number(block, "height")
            source_note = "source"
            if width is None or height is None:
                supplied = _rendered_size_for(block, design_evidence)
                if supplied is not None:
                    width, height, symbol = supplied
                    source_note = f"supplied design-evidence for key {symbol!r}"
                else:
                    unresolved = True
                    continue
            if min(width, height) < MIN_TOUCH_TARGET:
                undersized.append((path, line, width, height, source_note))

    if undersized:
        evidence = tuple(
            DesignEvidence(
                kind="fixed_size_interactive_control", source_path=inspector.relative(p), line=ln,
                observed=f"{w}x{h}", expected=f">= {MIN_TOUCH_TARGET:g}x{MIN_TOUCH_TARGET:g}",
                parser="regex-balanced-paren", confidence=Confidence.HIGH,
            )
            for p, ln, w, h, _note in undersized[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="BLOCKED", confidence=Confidence.HIGH,
            message=f"Found {len(undersized)} interactive control(s) with an explicit fixed size below "
                    f"{MIN_TOUCH_TARGET:g}x{MIN_TOUCH_TARGET:g} points.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Increase the control's explicit width/height to at least the HIG minimum touch target.",
        )

    if not wrapping_found or unresolved:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="UNKNOWN", confidence=Confidence.LOW,
            message="An interactive control was found, but its rendered size cannot be established from "
                    "source alone.",
            evidence=(DesignEvidence(kind="inspection", observed="no explicit fixed size determinable",
                                      expected="explicit width/height literal or supplied rendered-size evidence",
                                      parser="regex", confidence=Confidence.LOW, runtime_required=True),),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
            requested_evidence=("Actual rendered control size (via --design-evidence or manual measurement).",),
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="Every interactive control with an explicit fixed size met the minimum touch target.",
        evidence=(DesignEvidence(kind="inspection", observed="all explicit sizes >= minimum",
                                  expected=f">= {MIN_TOUCH_TARGET:g}x{MIN_TOUCH_TARGET:g}",
                                  parser="regex-balanced-paren", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def _icon_button_semantic_label(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.ACCESSIBILITY.ICON_BUTTON_SEMANTIC_LABEL")
    blocks = find_widget_invocations(inspector, "IconButton")
    if not blocks:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
            message="No IconButton controls were found locally.",
            evidence=(DesignEvidence(kind="inspection", observed="not found", expected="IconButton",
                                      parser="regex", confidence=Confidence.MEDIUM),),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
        )

    unlabeled = []
    for path, line, block, start, text in blocks:
        if has_named_arg(block, "tooltip") or has_named_arg(block, "semanticLabel"):
            continue
        window = text[max(0, start - 200):start]
        if "Semantics(" in window:
            continue
        unlabeled.append((path, line))

    if unlabeled:
        evidence = tuple(
            DesignEvidence(kind="icon_only_control", source_path=inspector.relative(p), line=ln,
                            observed="IconButton with no tooltip/semanticLabel/Semantics wrapper",
                            expected="tooltip, semanticLabel, or a wrapping Semantics(label: ...)",
                            parser="regex-balanced-paren", confidence=Confidence.HIGH)
            for p, ln in unlabeled[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="BLOCKED", confidence=Confidence.HIGH,
            message=f"Found {len(unlabeled)} icon-only control(s) with no accessible label.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Add a tooltip, semanticLabel, or wrap the control in Semantics(label: ...).",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.HIGH,
        message="Every IconButton found locally has an accessible label.",
        evidence=(DesignEvidence(kind="inspection", observed="all labeled", expected="accessible label",
                                  parser="regex-balanced-paren", confidence=Confidence.HIGH),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def _dynamic_type(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.ACCESSIBILITY.DYNAMIC_TYPE")
    matches = []
    for path in code_files(inspector):
        text = inspector.read_text(inspector.relative(path))
        if text is None:
            continue
        if _TEXT_SCALE_PATTERN.search(text):
            continue
        for match in _FONT_SIZE_PATTERN.finditer(text):
            line = text[:match.start()].count("\n") + 1
            matches.append((path, line, match.group(1)))

    if matches:
        evidence = tuple(
            DesignEvidence(kind="hardcoded_font_size", source_path=inspector.relative(p), line=ln,
                            observed=f"fontSize: {size}", expected="text-scaling API usage in the same file",
                            parser="regex", confidence=Confidence.MEDIUM)
            for p, ln, size in matches[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(matches)} hardcoded fontSize value(s) with no text-scaling API usage "
                    "detected in the same file(s); this is a heuristic risk signal, not proof Dynamic Type "
                    "is unsupported.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Use a text style that scales with the system font size, or verify Dynamic Type manually.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="No hardcoded fontSize without accompanying text-scaling API usage was found.",
        evidence=(DesignEvidence(kind="inspection", observed="not found", expected="unscaled hardcoded fontSize",
                                  parser="regex", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def evaluate(inspector: ProjectInspector, ruleset: Ruleset, design_evidence: dict | None = None) -> list[DesignFinding]:
    return [
        _touch_target_size(inspector, ruleset, design_evidence),
        _icon_button_semantic_label(inspector, ruleset),
        _dynamic_type(inspector, ruleset),
    ]
