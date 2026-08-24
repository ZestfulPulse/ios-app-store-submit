"""SAFE repair planners for malformed structured files (JSON / YAML / plist).

Every planner here follows the same shape: try a single, narrow, provably
semantics-preserving transform; if it makes the file parse, propose it as
SAFE. If the file is malformed but no such transform can be proven safe,
propose a MANUAL plan instead (never a silent no-op, never a guess).

No parser here ever invents a business value. YAML has no real parser in this
project (no new dependency is introduced for it, matching the rest of the
codebase's regex-based approach to pubspec.yaml) so its "repair" is scoped to
the one line the rest of the readiness tooling already understands: the
Flutter ``version:`` scalar.
"""

from __future__ import annotations

import json
import plistlib
import re
from pathlib import Path

from ..inspector import ProjectInspector
from .models import FixOperation, FixPlan, FixSafety

IGNORED_DIR_PARTS = {".git", ".dart_tool", "build", ".asc"}


def _strip_trailing_commas(text: str) -> str | None:
    """Remove commas that sit only before a closing ``]``/``}``, outside strings.

    Returns the repaired text, or None if no such comma was found (so callers
    can tell "nothing to do" apart from "produced a no-op repair").
    """
    result: list[str] = []
    in_string = False
    escape = False
    changed = False
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "]}":
                changed = True
                i += 1
                continue
        result.append(ch)
        i += 1
    return "".join(result) if changed else None


def plan_json_repairs(inspector: ProjectInspector) -> list[FixPlan]:
    plans: list[FixPlan] = []
    for path in sorted(inspector.root.rglob("*.json")):
        if not path.is_file():
            continue
        parts = path.relative_to(inspector.root).parts
        if any(part in IGNORED_DIR_PARTS for part in parts):
            continue
        relative = inspector.relative(path)
        text = inspector.read_text(relative)
        if text is None:
            continue
        try:
            json.loads(text)
            continue  # already valid JSON: nothing to repair
        except json.JSONDecodeError:
            pass

        repaired = _strip_trailing_commas(text)
        if repaired is not None:
            try:
                json.loads(repaired)
            except json.JSONDecodeError:
                repaired = None

        if repaired is not None:
            plans.append(FixPlan(
                fix_id=f"safe.repair_json_{relative.replace('/', '_')}",
                finding_id=f"structured.json.{relative}",
                safety=FixSafety.SAFE,
                title=f"Repair malformed JSON formatting in {relative}",
                target_path=relative,
                before=text,
                proposed_after=repaired,
                reason="Removed one or more trailing commas immediately before a closing bracket; "
                       "no key or value was added, removed, or reordered.",
                verification_rule=f"structured.json_valid:{relative}",
                operation=FixOperation.UPDATE_FORMAT,
                rule_id="JSON_TRAILING_COMMA",
                evidence=(f"{relative} fails json.loads before repair and parses after removing only trailing commas",),
            ))
        else:
            plans.append(FixPlan(
                fix_id=f"manual.repair_json_{relative.replace('/', '_')}",
                finding_id=f"structured.json.{relative}",
                safety=FixSafety.MANUAL,
                title=f"Malformed JSON in {relative} requires manual review",
                target_path=relative,
                before=text,
                proposed_after=None,
                reason="The file fails to parse and no provably semantics-preserving repair "
                       "(trailing-comma removal only) was sufficient to fix it.",
                verification_rule=f"structured.json_valid:{relative}",
                operation=FixOperation.UPDATE_FORMAT,
                rule_id="JSON_TRAILING_COMMA",
                evidence=(f"{relative} fails json.loads and no safe repair pattern applied",),
            ))
    return plans


_YAML_VERSION_LINE = re.compile(r"^([ \t]*version[ \t]*:[ \t]*)(.+?)[ \t]*$", re.MULTILINE)
_QUOTE_CHARS = "'\""


def plan_yaml_repairs(inspector: ProjectInspector) -> list[FixPlan]:
    plans: list[FixPlan] = []
    path = "pubspec.yaml"
    text = inspector.read_text(path)
    if text is None:
        return plans
    match = _YAML_VERSION_LINE.search(text)
    if not match:
        return plans
    raw_value = match.group(2)
    if len(raw_value) < 2 or raw_value[0] not in _QUOTE_CHARS or raw_value[-1] not in _QUOTE_CHARS:
        return plans  # unquoted or single-character values are outside this repair's scope
    if raw_value[0] == raw_value[-1]:
        return plans  # symmetric quoting is already handled by plan_safe_fixes' normalization

    inner = raw_value[1:-1]
    if re.fullmatch(r"\d+\.\d+\.\d+\+\d+", inner):
        before = match.group(0)
        after = f"{match.group(1)}{inner}"
        plans.append(FixPlan(
            fix_id="safe.repair_yaml_pubspec_version_quotes",
            finding_id="technical.pubspec_version",
            safety=FixSafety.SAFE,
            title="Repair mismatched YAML quote characters around the Flutter version",
            target_path=path,
            before=before,
            proposed_after=after,
            reason="Opening and closing quote characters differed around an otherwise unambiguous "
                   "X.Y.Z+N value; only the quoting is normalized away, the value itself is unchanged.",
            verification_rule="technical.pubspec_version",
            operation=FixOperation.NORMALIZE_VALUE,
            rule_id="PUBSPEC_VERSION",
            evidence=(f"pubspec.yaml:version had mismatched quotes ({raw_value[0]!r}/{raw_value[-1]!r}) "
                      f"around a valid X.Y.Z+N value ({inner})",),
        ))
        return plans

    plans.append(FixPlan(
        fix_id="manual.repair_yaml_pubspec_version",
        finding_id="technical.pubspec_version",
        safety=FixSafety.MANUAL,
        title="Ambiguous YAML version formatting requires manual review",
        target_path=path,
        before=raw_value,
        proposed_after=None,
        reason="The version scalar has mismatched quote characters and its inner content is not a "
               "valid X.Y.Z+N value either; a conservative repair cannot be proven without guessing intent.",
        verification_rule="technical.pubspec_version",
        operation=FixOperation.NORMALIZE_VALUE,
        rule_id="PUBSPEC_VERSION",
        evidence=(f"pubspec.yaml:version ({raw_value}) does not match a provably safe repair pattern",),
    ))
    return plans


_STRING_ELEMENT = re.compile(r"(<string>)(.*?)(</string>)", re.DOTALL)
_VALID_ENTITY_TAIL = re.compile(r"(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);")


def _escape_bare_ampersands(body: str) -> tuple[str, bool]:
    out: list[str] = []
    changed = False
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "&" and not _VALID_ENTITY_TAIL.match(body, i + 1):
            out.append("&amp;")
            changed = True
        else:
            out.append(ch)
        i += 1
    return "".join(out), changed


def plan_plist_repairs(inspector: ProjectInspector) -> list[FixPlan]:
    plans: list[FixPlan] = []
    path = "ios/Runner/Info.plist"
    text = inspector.read_text(path)
    if text is None:
        return plans
    try:
        plistlib.loads(text.encode("utf-8"))
        return plans  # already valid: nothing to repair
    except Exception:
        pass

    changed = False
    ambiguous = False

    def repair(m: re.Match[str]) -> str:
        nonlocal changed, ambiguous
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        if "<" in body:
            ambiguous = True
            return m.group(0)
        new_body, did_change = _escape_bare_ampersands(body)
        if did_change:
            changed = True
        return f"{open_tag}{new_body}{close_tag}"

    repaired = _STRING_ELEMENT.sub(repair, text)

    if ambiguous:
        plans.append(FixPlan(
            fix_id="manual.repair_plist_info",
            finding_id="structured.plist.ios/Runner/Info.plist",
            safety=FixSafety.MANUAL,
            title="Ambiguous plist markup requires manual review",
            target_path=path,
            before=text,
            proposed_after=None,
            reason="A <string> value contains a raw '<' character; whether it needs escaping or indicates "
                   "structurally corrupted/truncated markup cannot be distinguished automatically.",
            verification_rule="structured.plist_valid:ios/Runner/Info.plist",
            operation=FixOperation.UPDATE_FORMAT,
            rule_id="INFO_PLIST_MARKUP",
            evidence=("ios/Runner/Info.plist has an unescaped '<' inside a <string> element",),
        ))
        return plans

    if not changed:
        return plans

    try:
        plistlib.loads(repaired.encode("utf-8"))
    except Exception:
        return plans  # the attempted repair did not actually fix parsing; do not propose it

    plans.append(FixPlan(
        fix_id="safe.repair_plist_info_entities",
        finding_id="structured.plist.ios/Runner/Info.plist",
        safety=FixSafety.SAFE,
        title="Escape unescaped XML entities in Info.plist string values",
        target_path=path,
        before=text,
        proposed_after=repaired,
        reason="Bare '&' characters inside <string> values were escaped to '&amp;'; the represented "
               "text content is unchanged, only its XML encoding is corrected.",
        verification_rule="structured.plist_valid:ios/Runner/Info.plist",
        operation=FixOperation.UPDATE_FORMAT,
        rule_id="INFO_PLIST_MARKUP",
        evidence=("ios/Runner/Info.plist fails plistlib.loads before repair and parses after "
                  "escaping only bare '&' characters",),
    ))
    return plans
