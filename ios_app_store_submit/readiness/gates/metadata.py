"""Local metadata candidate checks. App Store Connect state is never guessed."""

from __future__ import annotations

import re

from ..inspector import ProjectInspector, evidence_for_line
from ..models import Evidence, Finding, Fixability, GateResult, Status

GATE = "METADATA"


def _finding(rule: str, title: str, status: Status, message: str, *, evidence=(), path=None,
             confidence=1.0, fixability=Fixability.MANUAL, suggested_fix=None, blocking=False) -> Finding:
    return Finding(
        finding_id=f"metadata.{rule.lower()}", gate=GATE, rule_id=rule, title=title,
        status=status, message=message, evidence=tuple(evidence), source_path=path,
        confidence=confidence, fixability=fixability, suggested_fix=suggested_fix,
        blocking=blocking,
    )


def _candidate_url(inspector: ProjectInspector, keys: tuple[str, ...], rule: str, title: str) -> Finding:
    info_path = "ios/Runner/Info.plist"
    values = inspector.plist_values(info_path)
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return _finding(rule, title, Status.PASS, f"Found local {title.lower()} candidate.",
                            evidence=(Evidence(kind="plist", path=info_path, key=key, observed=value.strip(),
                                                expected="URL candidate", source="project"),),
                            path=info_path, fixability=Fixability.NONE)
    matches = inspector.search(r"(?:privacy[_ -]?policy|support[_ -]?url)\s*[:=]\s*['\"]?(https?://[^'\"\s]+)")
    if matches:
        path, line, text = matches[0]
        return _finding(rule, title, Status.PASS, f"Found a {title.lower()} candidate in project text.",
                        evidence=(evidence_for_line(inspector, inspector.relative(path), line, text),),
                        path=inspector.relative(path), fixability=Fixability.NONE)
    return _finding(rule, title, Status.UNKNOWN,
                    f"No local {title.lower()} was found; App Store Connect/API state was not queried.",
                    evidence=(Evidence(kind="inspection", path=info_path, observed="not found",
                                        expected="candidate or ASC value", source="read-only inspection",
                                        command="read local project metadata"),),
                    path=info_path, confidence=0.75,
                    suggested_fix=f"Provide and verify a {title.lower()} before submission.")


def inspect_metadata(inspector: ProjectInspector) -> GateResult:
    findings: list[Finding] = []
    info_path = "ios/Runner/Info.plist"
    info = inspector.plist_values(info_path)
    display = info.get("CFBundleDisplayName") or info.get("CFBundleName")
    if isinstance(display, str) and display.strip() and "${" not in display:
        findings.append(_finding("DISPLAY_NAME", "App display-name candidate", Status.PASS,
                                 f"Found display-name candidate {display.strip()!r}.",
                                 evidence=(Evidence(kind="plist", path=info_path,
                                                     key="CFBundleDisplayName" if info.get("CFBundleDisplayName") else "CFBundleName",
                                                     observed=display.strip(), expected="non-empty name", source="project"),),
                                 path=info_path, fixability=Fixability.NONE))
    elif display:
        findings.append(_finding("DISPLAY_NAME", "App display-name candidate", Status.UNKNOWN,
                                 "The display-name value is unresolved or not parseable.",
                                 evidence=(Evidence(kind="plist", path=info_path, key="CFBundleDisplayName",
                                                     observed=display, expected="resolved value", source="project"),),
                                 path=info_path, confidence=0.9))
    else:
        findings.append(_finding("DISPLAY_NAME", "App display-name candidate", Status.UNKNOWN,
                                 "No local display-name candidate was found.",
                                 evidence=(Evidence(kind="plist", path=info_path, observed="not found",
                                                     expected="CFBundleDisplayName or CFBundleName", source="project"),),
                                 path=info_path, confidence=0.8))

    pubspec = inspector.read_text("pubspec.yaml") or ""
    version_match = re.search(r"^\s*version\s*:\s*(\S+)\s*$", pubspec, re.MULTILINE)
    if version_match and re.fullmatch(r"\d+\.\d+\.\d+\+\d+", version_match.group(1).strip("'\"")):
        value = version_match.group(1).strip("'\"")
        findings.append(_finding("VERSION", "Version candidate", Status.PASS,
                                 f"Found version candidate {value}.",
                                 evidence=(evidence_for_line(inspector, "pubspec.yaml",
                                                              pubspec[:version_match.start()].count("\n") + 1,
                                                              value, key="version"),), path="pubspec.yaml",
                                 fixability=Fixability.NONE))
        major_minor = value.rsplit("+", 1)[0]
        findings.append(_finding("BUILD_NUMBER", "Build number candidate", Status.PASS,
                                 f"Found build number candidate {value.rsplit('+', 1)[1]}.",
                                 evidence=(Evidence(kind="yaml", path="pubspec.yaml", key="version",
                                                     observed=value.rsplit("+", 1)[1], expected="numeric build number",
                                                     source="project"),), path="pubspec.yaml", fixability=Fixability.NONE))
    elif version_match:
        findings.append(_finding("VERSION", "Version candidate", Status.UNKNOWN,
                                 "The local version exists but is not parseable.",
                                 evidence=(Evidence(kind="yaml", path="pubspec.yaml", key="version",
                                                     observed=version_match.group(1), expected="X.Y.Z+N", source="project"),),
                                 path="pubspec.yaml"))
        findings.append(_finding("BUILD_NUMBER", "Build number candidate", Status.UNKNOWN,
                                 "The build number cannot be separated from an unparseable version.",
                                 evidence=(Evidence(kind="yaml", path="pubspec.yaml", key="version",
                                                     observed=version_match.group(1), expected="numeric build number", source="project"),),
                                 path="pubspec.yaml"))
    else:
        for rule, title in (("VERSION", "Version candidate"), ("BUILD_NUMBER", "Build number candidate")):
            findings.append(_finding(rule, title, Status.UNKNOWN,
                                     "No local version/build candidate was found; ASC state was not queried.",
                                     evidence=(Evidence(kind="yaml", path="pubspec.yaml", key="version",
                                                         observed="not found", expected="local value", source="project"),),
                                     path="pubspec.yaml"))

    pbx_path = "ios/Runner.xcodeproj/project.pbxproj"
    bundle = inspector.line_value(pbx_path, "PRODUCT_BUNDLE_IDENTIFIER")
    if bundle:
        value, line = bundle
        findings.append(_finding("BUNDLE_ID", "Bundle ID candidate", Status.PASS,
                                 f"Found bundle ID candidate {value}.",
                                 evidence=(evidence_for_line(inspector, pbx_path, line, value,
                                                              key="PRODUCT_BUNDLE_IDENTIFIER"),), path=pbx_path,
                                 fixability=Fixability.NONE))
    else:
        findings.append(_finding("BUNDLE_ID", "Bundle ID candidate", Status.UNKNOWN,
                                 "No local bundle ID candidate was found; ASC state was not queried.",
                                 evidence=(Evidence(kind="xcode_setting", path=pbx_path,
                                                     key="PRODUCT_BUNDLE_IDENTIFIER", observed="not found",
                                                     expected="bundle identifier", source="project"),), path=pbx_path))

    findings.append(_candidate_url(inspector, ("PrivacyPolicyURL", "PrivacyPolicy", "privacyPolicyURL"),
                                   "PRIVACY_POLICY", "privacy policy URL candidate"))
    findings.append(_candidate_url(inspector, ("SupportURL", "SupportUrl", "supportURL"),
                                   "SUPPORT_URL", "support URL candidate"))

    localization_paths = [
        path for pattern in ("ios/**/*.lproj", "lib/**/l10n", "assets/**/locales")
        for path in inspector.root.glob(pattern) if path.is_dir()
    ]
    localization_dirs = sorted({inspector.relative(path) for path in localization_paths})
    if localization_dirs:
        findings.append(_finding("LOCALIZATIONS", "Localization directories", Status.PASS,
                                 f"Found {len(localization_dirs)} localization directory/directories.",
                                 evidence=tuple(Evidence(kind="directory", path=path, observed="present",
                                                          expected="localization directory", source="filesystem")
                                                 for path in localization_dirs),
                                 fixability=Fixability.NONE))
    else:
        findings.append(_finding("LOCALIZATIONS", "Localization directories", Status.ADVISORY,
                                 "No localization directory was found in the local project.",
                                 evidence=(Evidence(kind="directory", path="ios", observed="not found",
                                                     expected="optional localization directory", source="filesystem"),),
                                 fixability=Fixability.NONE))

    strings = inspector.files(("**/InfoPlist.strings", "**/*.lproj/InfoPlist.strings"))
    if strings:
        findings.append(_finding("INFOPLIST_STRINGS", "InfoPlist.strings", Status.PASS,
                                 "Found InfoPlist.strings localization file(s).",
                                 evidence=tuple(Evidence(kind="file", path=inspector.relative(path), observed="present",
                                                          expected="InfoPlist.strings", source="filesystem") for path in strings),
                                 fixability=Fixability.NONE))
        name_matches = inspector.search(r"[\"']?(?:CFBundleDisplayName|CFBundleName)[\"']?\s*=", strings)
        findings.append(_finding("LOCALIZED_APP_NAME", "App-name localization availability",
                                 Status.PASS if name_matches else Status.UNKNOWN,
                                 "Found localized app-name keys." if name_matches else "InfoPlist.strings exists but no localized app-name key was found.",
                                 evidence=tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                                 for path, line, text in name_matches) or
                                           (Evidence(kind="file", path=inspector.relative(strings[0]), observed="no app-name key",
                                                     expected="CFBundleDisplayName or CFBundleName", source="project"),),
                                 fixability=Fixability.NONE if name_matches else Fixability.MANUAL))
    else:
        findings.append(_finding("INFOPLIST_STRINGS", "InfoPlist.strings", Status.ADVISORY,
                                 "No InfoPlist.strings file was found locally.",
                                 evidence=(Evidence(kind="file", path="ios", observed="not found",
                                                     expected="optional InfoPlist.strings", source="filesystem"),),
                                 fixability=Fixability.NONE))
        findings.append(_finding("LOCALIZED_APP_NAME", "App-name localization availability", Status.UNKNOWN,
                                 "App-name localization cannot be established without InfoPlist.strings.",
                                 evidence=(Evidence(kind="inspection", path="ios", observed="not inspected",
                                                     expected="localized app name", source="read-only inspection"),)))
    return GateResult(GATE, findings)
