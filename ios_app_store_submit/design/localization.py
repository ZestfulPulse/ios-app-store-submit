"""HIG localization checks: hardcoded strings, missing keys, fixed-width text.

Never invents a translation and never auto-localizes user-authored copy.
A hardcoded-string match stays RISK (some literals are intentionally
non-localized, e.g. debug/log text); a missing key across two parsed
resource files is a directly observable, deterministic fact.
"""

from __future__ import annotations

import re

from ..readiness.inspector import ProjectInspector
from .inspector import code_files, extract_named_number, find_widget_invocations, load_localization_resource
from .models import Confidence, DesignEvidence, DesignFinding, Ruleset

_HARDCODED_TEXT_PATTERN = re.compile(r"\bText\s*\(\s*['\"]([^'\"]{2,})['\"]")
FIXED_CONTAINER_MAX_WIDTH = 150.0


def _finding_id(rule_id: str) -> str:
    return f"design.{rule_id.lower().replace('.', '_')}"


def _hardcoded_string(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.LOCALIZATION.HARDCODED_STRING")
    matches = []
    for path in code_files(inspector):
        text = inspector.read_text(inspector.relative(path))
        if text is None:
            continue
        for match in _HARDCODED_TEXT_PATTERN.finditer(text):
            line = text[:match.start()].count("\n") + 1
            matches.append((path, line, match.group(1)))

    if matches:
        evidence = tuple(
            DesignEvidence(kind="hardcoded_user_visible_string", source_path=inspector.relative(p), line=ln,
                            observed=value, expected="a localization delegate/call instead of a raw literal",
                            parser="regex", confidence=Confidence.MEDIUM)
            for p, ln, value in matches[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(matches)} string literal(s) passed directly to Text(); this is a heuristic "
                    "risk signal for missing localization, not proof (some literals are intentionally "
                    "non-localized).",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Route user-visible text through a localization delegate.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="No string literal passed directly to Text() was found.",
        evidence=(DesignEvidence(kind="inspection", observed="not found", expected="raw string literal in Text()",
                                  parser="regex", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def _missing_key(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.LOCALIZATION.MISSING_KEY")
    arb_files = inspector.files(("**/*.arb",))
    resources = {}
    for path in arb_files:
        relative = inspector.relative(path)
        data = load_localization_resource(inspector, relative)
        if data is None:
            continue
        keys = {key for key in data if not key.startswith("@")}
        resources[relative] = keys

    if len(resources) < 2:
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="UNKNOWN", confidence=Confidence.LOW,
            message="Fewer than two parseable localization resource files were found locally; a "
                    "cross-language key comparison cannot be made.",
            evidence=(DesignEvidence(kind="inspection", observed=f"{len(resources)} resource file(s)",
                                      expected="2 or more .arb resource files", parser="json",
                                      confidence=Confidence.LOW),),
            source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
            fixability=rule.fixability,
        )

    all_keys = set()
    for keys in resources.values():
        all_keys |= keys

    missing = []
    for path, keys in sorted(resources.items()):
        for key in sorted(all_keys - keys):
            missing.append((path, key))

    if missing:
        evidence = tuple(
            DesignEvidence(kind="missing_localization_key", source_path=path, symbol=key,
                            observed="key absent", expected="key present in every resource file",
                            parser="json", confidence=Confidence.HIGH)
            for path, key in missing[:20]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="BLOCKED", confidence=Confidence.HIGH,
            message=f"Found {len(missing)} localization key gap(s) across {len(resources)} resource files.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Add the missing key(s) to every language's resource file.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.HIGH,
        message=f"All {len(all_keys)} localization key(s) are present in every one of {len(resources)} "
                "resource files found.",
        evidence=(DesignEvidence(kind="inspection", observed="no key gaps", expected="consistent key sets",
                                  parser="json", confidence=Confidence.HIGH),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def _fixed_text_container(inspector: ProjectInspector, ruleset: Ruleset) -> DesignFinding:
    rule = ruleset.rule("DESIGN.LOCALIZATION.FIXED_TEXT_CONTAINER")
    files = code_files(inspector)
    matches = []
    for wrapper in ("SizedBox", "Container"):
        for path, line, block, _start, _text in find_widget_invocations(inspector, wrapper, files):
            if "Text(" not in block:
                continue
            width = extract_named_number(block, "width")
            if width is None or width > FIXED_CONTAINER_MAX_WIDTH:
                continue
            matches.append((path, line, width))

    if matches:
        evidence = tuple(
            DesignEvidence(kind="fixed_width_text_container", source_path=inspector.relative(p), line=ln,
                            observed=f"width: {w:g}", expected=f"width >= {FIXED_CONTAINER_MAX_WIDTH:g} or flexible sizing",
                            parser="regex-balanced-paren", confidence=Confidence.MEDIUM)
            for p, ln, w in matches[:10]
        )
        return DesignFinding(
            finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
            title=rule.title, status="RISK", confidence=Confidence.MEDIUM,
            message=f"Found {len(matches)} small fixed-width container(s) wrapping text; this risks "
                    "clipping once translated into a longer-running language.",
            evidence=evidence, source_url=rule.source_url, ruleset_id=ruleset.ruleset_id,
            check_type=rule.evaluation_type, fixability=rule.fixability,
            suggested_fix="Allow the text container to size flexibly instead of a small fixed width.",
        )

    return DesignFinding(
        finding_id=_finding_id(rule.rule_id), rule_id=rule.rule_id, hig_area=rule.hig_area,
        title=rule.title, status="PASS", confidence=Confidence.MEDIUM,
        message="No small fixed-width container wrapping text was found.",
        evidence=(DesignEvidence(kind="inspection", observed="not found", expected="small fixed-width text container",
                                  parser="regex-balanced-paren", confidence=Confidence.MEDIUM),),
        source_url=rule.source_url, ruleset_id=ruleset.ruleset_id, check_type=rule.evaluation_type,
        fixability=rule.fixability,
    )


def evaluate(inspector: ProjectInspector, ruleset: Ruleset, design_evidence: dict | None = None) -> list[DesignFinding]:
    return [
        _hardcoded_string(inspector, ruleset),
        _missing_key(inspector, ruleset),
        _fixed_text_container(inspector, ruleset),
    ]
