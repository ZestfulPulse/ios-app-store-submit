"""Pure planners for narrowly scoped, local, deterministic fixes."""

from __future__ import annotations

import re
from pathlib import Path

from ..inspector import ProjectInspector
from .models import FixOperation, FixPlan, FixSafety


VERSION_LINE = re.compile(r"^(\s*version\s*:\s*)([\"'])(\d+\.\d+\.\d+\+\d+)(\2)(\s*)$", re.MULTILINE)
DISPLAY_NAME_XML = re.compile(
    r"(<key>CFBundleDisplayName</key>\s*<string>)([^<]*?)(</string>)", re.MULTILINE
)


def _line_ending(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def plan_safe_fixes(inspector: ProjectInspector) -> list[FixPlan]:
    plans: list[FixPlan] = []
    pubspec_path = inspector.path("pubspec.yaml")
    pubspec = inspector.read_text("pubspec.yaml")
    if pubspec is not None:
        match = VERSION_LINE.search(pubspec)
        if match:
            before = match.group(0)
            after = f"{match.group(1)}{match.group(3)}{match.group(5)}"
            if before != after:
                plans.append(FixPlan(
                    fix_id="safe.normalize_pubspec_version",
                    finding_id="technical.pubspec_version",
                    safety=FixSafety.SAFE,
                    title="Normalize Flutter version/build formatting",
                    target_path="pubspec.yaml",
                    before=before,
                    proposed_after=after,
                    reason="The quoted value is an unambiguous X.Y.Z+N Flutter version and can be normalized locally.",
                    verification_rule="technical.pubspec_version",
                    operation=FixOperation.NORMALIZE_VALUE,
                    rule_id="PUBSPEC_VERSION",
                    evidence=(f"pubspec.yaml:version quoted value matches X.Y.Z+N ({match.group(3)})",),
                ))

    info_path = inspector.path("ios/Runner/Info.plist")
    info = inspector.read_text("ios/Runner/Info.plist")
    if info is not None:
        match = DISPLAY_NAME_XML.search(info)
        if match and match.group(2) != match.group(2).strip() and match.group(2).strip():
            before = match.group(0)
            after = f"{match.group(1)}{match.group(2).strip()}{match.group(3)}"
            plans.append(FixPlan(
                fix_id="safe.normalize_display_name",
                finding_id="metadata.display_name",
                safety=FixSafety.SAFE,
                title="Normalize local display-name formatting",
                target_path="ios/Runner/Info.plist",
                before=before,
                proposed_after=after,
                reason="Only surrounding whitespace is removed from an existing local display-name value.",
                verification_rule="metadata.display_name",
                operation=FixOperation.UPDATE_FORMAT,
                rule_id="DISPLAY_NAME",
                evidence=(f"Info.plist:CFBundleDisplayName has surrounding whitespace ({match.group(2)!r})",),
            ))
    return plans


def plan_localization_scaffold(inspector: ProjectInspector) -> list[FixPlan]:
    """Auto-propose a single conventional, empty locale directory when none exists.

    This never writes any file content, so it can resolve the purely-structural
    ``metadata.localizations`` finding (directory presence) but cannot resolve
    findings that require actual localized text (``INFOPLIST_STRINGS``,
    ``LOCALIZED_APP_NAME``) or any other content-required finding.
    """
    if not inspector.exists("ios"):
        return []
    if list(inspector.root.glob("ios/**/*.lproj")):
        return []
    target = "ios/Runner/en.lproj"
    if inspector.exists(target):
        return []
    return [FixPlan(
        fix_id="safe.scaffold_default_locale",
        finding_id="metadata.localizations",
        safety=FixSafety.SAFE,
        title="Create the default en.lproj localization directory",
        target_path=target,
        before=None,
        proposed_after="<empty directory created>",
        reason="No .lproj directory exists anywhere under ios/; en.lproj is the conventional Flutter/iOS "
               "default locale directory and is created empty, with no localized content.",
        verification_rule=f"scaffold:{target}",
        operation=FixOperation.CREATE,
        rule_id="LOCALIZATIONS",
        evidence=("No localization directory exists locally; target path is deterministic and conventional.",),
    )]


def plan_empty_directory(inspector: ProjectInspector, relative_path: str, *, finding_id: str,
                         title: str, reason: str, verification_rule: str, rule_id: str | None = None) -> FixPlan:
    """Create a plan for an explicitly requested empty directory scaffold.

    This helper is intentionally not called automatically by the current gates: a
    missing app directory is not enough evidence that the user wants it created.
    """
    target = inspector.path(relative_path).resolve()
    try:
        target.relative_to(inspector.root)
    except ValueError as exc:
        raise ValueError("scaffold target must remain inside the project") from exc
    if target.exists():
        raise ValueError("scaffold target already exists")
    if relative_path.startswith(".") or "/.." in relative_path or relative_path == "..":
        raise ValueError("hidden or parent-traversing scaffold paths are not automatic SAFE targets")
    return FixPlan(
        fix_id=f"safe.scaffold_{relative_path.replace('/', '_')}",
        finding_id=finding_id,
        safety=FixSafety.SAFE,
        title=title,
        target_path=relative_path,
        before=None,
        proposed_after="<empty directory created>",
        reason=reason,
        verification_rule=verification_rule,
        operation=FixOperation.CREATE,
        rule_id=rule_id,
        evidence=(f"{relative_path} does not exist locally and is a non-destructive scaffold target",),
    )
