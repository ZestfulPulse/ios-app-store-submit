"""HIG interaction checks: gesture-only affordances, permission-request context.

Both checks are heuristic text-window signals and stay at RISK: neither a
gesture-only construct nor a permission call missing nearby explanatory
text is proof of an actual UX defect, only a conservative risk signal.
"""

from __future__ import annotations

import re

from ..readiness.inspector import ProjectInspector
from .inspector import code_files, has_named_arg
from .models import Confidence, DesignEvidence, DesignFinding, Ruleset

_PERMISSION_REQUEST_PATTERN = re.compile(
    r"\bPermission\.\w+\.request\s*\(|\.requestPermission\s*\(|\brequestPermission\s*\("
)
_CONTEXT_WINDOW = 300
_AFFORDANCE_WINDOW = 150


def _finding_id(rule_id: str) -> str:
    return f"design.{rule_id.lower().replace('.', '_')}"


def _gesture_only(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.INTERACTION.GESTURE_ONLY")
    from .inspector import find_widget_invocations

    blocks = find_widget_invocations(inspector, "GestureDetector")
    tap_blocks = [(p, ln, block, start, text) for p, ln, block, start, text in blocks if has_named_arg(block, "onTap")]

    if not tap_blocks:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
            message="No GestureDetector(onTap: ...) construct was found locally.",
            evidence=(DesignEvidence(kind="inspection", observed="not found", expected="GestureDetector(onTap: ...)",
                                      parser="regex", confidence=Confidence.MEDIUM),),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
        )

    unresolved = []
    for path, line, block, start, text in tap_blocks:
        window = text[max(0, start - _AFFORDANCE_WINDOW):start]
        if "Semantics(" in window or "Button" in block:
            continue
        unresolved.append((path, line))

    if unresolved:
        evidence = tuple(
            DesignEvidence(kind="gesture_only_interaction", source_path=inspector.relative(p), line=ln,
                            observed="GestureDetector(onTap: ...) with no nearby Semantics/button affordance",
                            expected="a Semantics(...) wrapper or a semantic button-role child",
                            parser="regex", confidence=Confidence.MEDIUM)
            for p, ln in unresolved[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(unresolved)} gesture-only interaction(s) with no accessibility affordance "
                    "found nearby; this is a heuristic risk signal, not proof there is no alternative.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Wrap the gesture in Semantics(...) or use a semantic button-role widget.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="Every gesture-only interaction found has a nearby accessibility affordance.",
        evidence=(DesignEvidence(kind="inspection", observed="all resolved", expected="accessibility affordance",
                                  parser="regex", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def _permission_context(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.INTERACTION.PERMISSION_CONTEXT")
    matches = []
    for path in code_files(inspector):
        text = inspector.read_text(inspector.relative(path))
        if text is None:
            continue
        for match in _PERMISSION_REQUEST_PATTERN.finditer(text):
            window = text[max(0, match.start() - _CONTEXT_WINDOW):match.start()]
            if "showDialog(" in window or "AlertDialog(" in window or "Text(" in window:
                continue
            line = text[:match.start()].count("\n") + 1
            matches.append((path, line, match.group(0)))

    if matches:
        evidence = tuple(
            DesignEvidence(kind="permission_request_without_context", source_path=inspector.relative(p), line=ln,
                            observed=call, expected="a preceding dialog/explanatory text construct",
                            parser="regex", confidence=Confidence.MEDIUM)
            for p, ln, call in matches[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(matches)} permission-request call(s) with no dialog/explanatory text "
                    "construct found in the preceding source window; this is a heuristic risk signal, not "
                    "proof no context is ever shown to the user.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Show explanatory context (a dialog or in-line text) before requesting the permission.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="No permission-request call without nearby explanatory context was found.",
        evidence=(DesignEvidence(kind="inspection", observed="not found", expected="uncontextualized permission request",
                                  parser="regex", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def evaluate(inspector: ProjectInspector, ruleset: Ruleset, design_evidence: dict | None = None) -> list[DesignFinding]:
    return [
        _gesture_only(inspector, ruleset),
        _permission_context(inspector, ruleset),
    ]
