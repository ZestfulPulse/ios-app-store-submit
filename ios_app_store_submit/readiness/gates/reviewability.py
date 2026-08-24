"""Conservative reviewability checks for login, notes, backend, and permissions."""

from __future__ import annotations

import re

from ..inspector import ProjectInspector, evidence_for_line
from ..models import Evidence, Finding, Fixability, GateResult, Status

GATE = "REVIEWABILITY"


def _finding(rule: str, title: str, status: Status, message: str, *, evidence=(), path=None,
             confidence=1.0, fixability=Fixability.MANUAL, suggested_fix=None, blocking=False) -> Finding:
    return Finding(
        finding_id=f"reviewability.{rule.lower()}", gate=GATE, rule_id=rule, title=title,
        status=status, message=message, evidence=tuple(evidence), source_path=path,
        confidence=confidence, fixability=fixability, suggested_fix=suggested_fix,
        blocking=blocking,
    )


CODE_SUFFIXES = {".dart", ".swift", ".m", ".mm", ".storyboard", ".xib", ".json", ".yaml", ".yml", ".plist"}


def inspect_reviewability(inspector: ProjectInspector) -> GateResult:
    findings: list[Finding] = []
    code_files = [path for path in inspector.all_text_files() if path.suffix.lower() in CODE_SUFFIXES]
    login_matches = inspector.search(r"\b(?:login|log\s*in|sign\s*in|authenticate|authentication|authprovider|firebaseauth)\b", code_files)
    if login_matches:
        login_evidence = tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                for path, line, text in login_matches[:10])
        findings.append(_finding("LOGIN", "Possible login functionality", Status.RISK,
                                 "Login/authentication functionality appears possible; review access should be checked.",
                                 evidence=login_evidence, path=inspector.relative(login_matches[0][0]),
                                 confidence=0.82, suggested_fix="Provide a working demo/review account and exact review steps."))
    else:
        findings.append(_finding("LOGIN", "Possible login functionality", Status.UNKNOWN,
                                 "Login functionality could not be established confidently from local source.",
                                 evidence=(Evidence(kind="inspection", path=".", observed="no confident match",
                                                     expected="login decision", source="read-only inspection",
                                                     command="scan source for conservative authentication indicators"),),
                                 confidence=0.55))

    # A login form's username/password fields are not a demo account. Only
    # documentation/configuration is considered evidence of supplied review access.
    review_files = [path for path in inspector.all_text_files()
                    if path.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json", ".plist", ".env"}]
    review_matches = inspector.search(r"(?:demo\s+(?:account|credentials?)|review\s+(?:account|credentials?|notes?)|test\s+account|username\s*[:=]|password\s*[:=])", review_files)
    if review_matches:
        findings.append(_finding("REVIEW_INFO", "Demo/review-account configuration", Status.PASS,
                                 "Found a possible demo/review-account or review-notes candidate.",
                                 evidence=tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                                 for path, line, text in review_matches[:10]),
                                 path=inspector.relative(review_matches[0][0]), fixability=Fixability.NONE))
    elif login_matches:
        findings.append(_finding("REVIEW_INFO", "Demo/review-account configuration", Status.BLOCKED,
                                 "Login appears possible but no demo/review-account configuration or notes candidate was found.",
                                 evidence=tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                                 for path, line, text in login_matches[:5]),
                                 path=inspector.relative(login_matches[0][0]),
                                 suggested_fix="Document a non-production demo account and review steps, or make the login path unnecessary for review.",
                                 blocking=True))
    else:
        findings.append(_finding("REVIEW_INFO", "Demo/review-account configuration", Status.UNKNOWN,
                                 "Demo/review-account availability cannot be assessed without confirmed login behavior.",
                                 evidence=(Evidence(kind="inspection", path=".", observed="not established",
                                                     expected="review information when login is required", source="read-only inspection"),),
                                 confidence=0.55))

    note_matches = inspector.search(r"(?:review[_ -]?notes?|app[_ -]?review|review instructions?)")
    findings.append(_finding("REVIEW_NOTES", "Review-notes candidate", Status.PASS if note_matches else Status.UNKNOWN,
                             "Found review-notes candidate(s)." if note_matches else "No local review-notes candidate was found; ASC review details were not queried.",
                             evidence=tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                             for path, line, text in note_matches[:10]) or
                                       (Evidence(kind="inspection", path=".", observed="not found",
                                                 expected="optional review notes", source="read-only inspection",
                                                 command="scan local text files"),),
                             confidence=0.85 if note_matches else 0.7,
                             fixability=Fixability.NONE if note_matches else Fixability.MANUAL))

    backend_files = [path for path in code_files if path.suffix.lower() != ".plist"]
    backend_matches = inspector.search(r"(?:https?://|API[_-]?(?:BASE_)?URL|baseUrl|backendUrl)", backend_files)
    findings.append(_finding("BACKEND", "Backend URL/environment dependency", Status.ADVISORY,
                             "Backend URL or environment dependency is detectable." if backend_matches else "No backend URL/environment dependency was detected by the local scan.",
                             evidence=tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                             for path, line, text in backend_matches[:10]) or
                                       (Evidence(kind="inspection", path=".", observed="not detected",
                                                 expected="backend dependency decision", source="read-only inspection"),),
                             confidence=0.8 if backend_matches else 0.6,
                             suggested_fix="Verify the review build uses a reachable, non-production backend." if backend_matches else None))

    info_path = "ios/Runner/Info.plist"
    info = inspector.plist_values(info_path)
    permission_keys = sorted(key for key in info if isinstance(key, str) and (
        key.endswith("UsageDescription") or key.startswith("NSPhoto")
    ))
    if permission_keys:
        findings.append(_finding("PERMISSIONS", "Usage-description keys", Status.PASS,
                                 "Found usage-description keys for declared permissions.",
                                 evidence=tuple(Evidence(kind="plist", path=info_path, key=key,
                                                          observed=info[key], expected="reviewable permission rationale",
                                                          source="project") for key in permission_keys),
                                 path=info_path, fixability=Fixability.NONE))
    else:
        permission_code = inspector.search(r"(?:camera|location|contacts?|calendar|microphone|photos?|bluetooth|notification)", code_files)
        findings.append(_finding("PERMISSIONS", "Usage-description keys", Status.UNKNOWN if permission_code else Status.ADVISORY,
                                 "Permission-related code was found but no matching usage-description key was found." if permission_code else "No usage-description keys were found locally.",
                                 evidence=tuple(evidence_for_line(inspector, inspector.relative(path), line, text)
                                                 for path, line, text in permission_code[:10]) or
                                           (Evidence(kind="plist", path=info_path, observed="not found",
                                                     expected="permission usage descriptions", source="project"),),
                                 path=info_path, confidence=0.75 if permission_code else 0.65,
                                 suggested_fix="Review required permission usage-description keys." if permission_code else None))
    return GateResult(GATE, findings)
