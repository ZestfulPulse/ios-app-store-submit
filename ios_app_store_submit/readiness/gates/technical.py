"""Technical project-shape checks. These checks never invoke Xcode or signing tools."""

from __future__ import annotations

import re

from ..inspector import ProjectInspector, evidence_for_line
from ..models import Evidence, Finding, Fixability, GateResult, Status

GATE = "TECHNICAL"
PBX_PATH = "ios/Runner.xcodeproj/project.pbxproj"


def _finding(rule: str, title: str, status: Status, message: str, *, evidence=(), path=None,
             confidence=1.0, fixability=Fixability.MANUAL, suggested_fix=None, blocking=False) -> Finding:
    return Finding(
        finding_id=f"technical.{rule.lower()}", gate=GATE, rule_id=rule, title=title,
        status=status, message=message, evidence=tuple(evidence), source_path=path,
        confidence=confidence, fixability=fixability, suggested_fix=suggested_fix,
        blocking=blocking,
    )


def _presence(inspector: ProjectInspector, relative: str, rule: str, title: str, missing_status=Status.ADVISORY) -> Finding:
    if inspector.exists(relative):
        return _finding(rule, title, Status.PASS, f"Found {relative}.", path=relative,
                        evidence=(Evidence(kind="file", path=relative, observed="present", expected="present", source="filesystem"),),
                        fixability=Fixability.NONE)
    return _finding(rule, title, missing_status, f"Could not find {relative}.", path=relative,
                    evidence=(Evidence(kind="file", path=relative, observed="missing", expected="present", source="filesystem"),),
                    suggested_fix=f"Add {relative}." if missing_status is not Status.UNKNOWN else None,
                    blocking=missing_status is Status.BLOCKED)


def _pubspec_version(inspector: ProjectInspector) -> Finding:
    path = "pubspec.yaml"
    text = inspector.read_text(path)
    if text is None:
        return _finding("PUBSPEC_VERSION", "Flutter version/build", Status.BLOCKED,
                        "Cannot inspect Flutter version because pubspec.yaml is missing.",
                        evidence=(Evidence(kind="file", path=path, observed="missing", expected="present", source="filesystem"),),
                        path=path, suggested_fix="Add a version: X.Y.Z+N entry to pubspec.yaml.", blocking=True)
    match = re.search(r"^\s*version\s*:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        return _finding("PUBSPEC_VERSION", "Flutter version/build", Status.BLOCKED,
                        "pubspec.yaml has no Flutter version/build entry.",
                        evidence=(Evidence(kind="yaml", path=path, key="version", observed=None, expected="X.Y.Z+N", source="project"),),
                        path=path, suggested_fix="Add version: X.Y.Z+N to pubspec.yaml.", blocking=True)
    value = match.group(1).strip().strip("'\"")
    evidence = (evidence_for_line(inspector, path, text[:match.start()].count("\n") + 1, value, key="version"),)
    if not re.fullmatch(r"\d+\.\d+\.\d+\+\d+", value):
        return _finding("PUBSPEC_VERSION", "Flutter version/build", Status.UNKNOWN,
                        f"Flutter version/build value is not parseable as X.Y.Z+N: {value}.",
                        evidence=evidence, path=path, confidence=0.95,
                        suggested_fix="Use a semantic Flutter version followed by a numeric build, such as 1.2.3+4.")
    return _finding("PUBSPEC_VERSION", "Flutter version/build", Status.PASS,
                    f"Parsed Flutter version/build {value}.", evidence=evidence, path=path,
                    fixability=Fixability.NONE)


def inspect_technical(inspector: ProjectInspector) -> GateResult:
    findings: list[Finding] = []
    findings.append(_presence(inspector, "ios/Runner.xcodeproj", "PROJECT", "Runner Xcode project", Status.BLOCKED))
    findings.append(_presence(inspector, "pubspec.yaml", "PUBSPEC", "Flutter pubspec", Status.BLOCKED))
    findings.append(_pubspec_version(inspector))

    pbx_text = inspector.read_text(PBX_PATH)
    if pbx_text is None:
        findings.append(_finding(
            "PBXPROJ", "Xcode project file", Status.BLOCKED,
            "Cannot inspect Xcode build settings because project.pbxproj is missing.",
            evidence=(Evidence(kind="file", path=PBX_PATH, observed="missing", expected="present", source="filesystem"),),
            path=PBX_PATH, suggested_fix="Restore the Runner project file.", blocking=True,
        ))
        return GateResult(GATE, findings)

    def setting(rule: str, key: str, title: str, *, required=False) -> None:
        result = inspector.line_value(PBX_PATH, key)
        if result is None:
            status = Status.BLOCKED if required else Status.ADVISORY
            findings.append(_finding(
                rule, title, status, f"{key} is not present in the Xcode project.",
                evidence=(Evidence(kind="xcode_setting", path=PBX_PATH, key=key, observed=None,
                                    expected="present", source="project"),),
                path=PBX_PATH, suggested_fix=f"Define {key} in the Runner target configuration.", blocking=required,
            ))
            return
        value, line = result
        evidence = (evidence_for_line(inspector, PBX_PATH, line, value, key=key),)
        if not value and required:
            findings.append(_finding(
                rule, title, Status.BLOCKED, f"{key} is present but empty in the Xcode project.",
                evidence=evidence, path=PBX_PATH, suggested_fix=f"Set a concrete {key} in the Runner target configuration.", blocking=True,
            ))
        elif not value or "$(" in value or value.startswith("<"):
            findings.append(_finding(
                rule, title, Status.UNKNOWN, f"{key} was found but could not be interpreted: {value!r}.",
                evidence=evidence, path=PBX_PATH, confidence=0.9,
                suggested_fix=f"Resolve the {key} value in the Runner target configuration.",
            ))
        else:
            findings.append(_finding(rule, title, Status.PASS, f"Found {key}={value}.", evidence=evidence,
                                     path=PBX_PATH, fixability=Fixability.NONE))

    setting("BUNDLE_ID", "PRODUCT_BUNDLE_IDENTIFIER", "Bundle ID", required=True)
    setting("TEAM_ID", "DEVELOPMENT_TEAM", "Development team")
    setting("DEVICE_FAMILY", "TARGETED_DEVICE_FAMILY", "Targeted device family")
    findings.append(_presence(inspector, "ios/Runner/Info.plist", "INFO_PLIST", "Runner Info.plist", Status.BLOCKED))

    if inspector.exists("ios/Runner/Runner.entitlements"):
        findings.append(_finding(
            "ENTITLEMENTS", "Entitlements file", Status.ADVISORY,
            "An entitlements file is present; its values are recorded but not validated in Phase 1.",
            evidence=(Evidence(kind="file", path="ios/Runner/Runner.entitlements", observed="present", expected="reviewed", source="filesystem"),),
            path="ios/Runner/Runner.entitlements", fixability=Fixability.NONE,
        ))
    else:
        findings.append(_finding(
            "ENTITLEMENTS", "Entitlements file", Status.ADVISORY,
            "No Runner entitlements file was found; this is informational in Phase 1.",
            evidence=(Evidence(kind="file", path="ios/Runner/Runner.entitlements", observed="missing", expected="optional", source="filesystem"),),
            path="ios/Runner/Runner.entitlements", fixability=Fixability.NONE,
        ))

    setting("DEPLOYMENT_TARGET", "IPHONEOS_DEPLOYMENT_TARGET", "iOS deployment target")
    if re.search(r"name\s*=\s*Release;", pbx_text):
        findings.append(_finding("RELEASE_CONFIG", "Release configuration", Status.PASS,
                                 "A Release configuration is present.",
                                 evidence=(Evidence(kind="xcode_configuration", path=PBX_PATH,
                                                     observed="Release", expected="present", source="project"),),
                                 path=PBX_PATH, fixability=Fixability.NONE))
    else:
        findings.append(_finding("RELEASE_CONFIG", "Release configuration", Status.BLOCKED,
                                 "No Release configuration was found.",
                                 evidence=(Evidence(kind="xcode_configuration", path=PBX_PATH,
                                                     observed="missing", expected="Release", source="project"),),
                                 path=PBX_PATH, suggested_fix="Restore the Release build configuration.", blocking=True))

    runner_match = re.search(r"(?:isa\s*=\s*PBXNativeTarget|PBXNativeTarget)[^;]*.*?name\s*=\s*Runner;", pbx_text, re.DOTALL)
    if runner_match:
        findings.append(_finding("RUNNER_TARGET", "Runner target", Status.PASS,
                                 "Identified a Runner native target.",
                                 evidence=(Evidence(kind="xcode_target", path=PBX_PATH, observed="Runner",
                                                     expected="present", source="project"),),
                                 path=PBX_PATH, fixability=Fixability.NONE))
    else:
        findings.append(_finding("RUNNER_TARGET", "Runner target", Status.UNKNOWN,
                                 "Could not confidently identify the Runner native target.",
                                 evidence=(Evidence(kind="xcode_target", path=PBX_PATH, observed="not identified",
                                                     expected="Runner", source="project"),),
                                 path=PBX_PATH, confidence=0.8))
    return GateResult(GATE, findings)
