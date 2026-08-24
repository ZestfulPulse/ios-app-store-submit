"""Phase 4: orchestrates Privacy Intelligence evidence collection, candidate
mapping, and contradiction detection into one PrivacyIntelligenceResult.

PRIVACY_GATE PASS means "no unresolved privacy-relevant fact and no
blocking structural defect was found by the currently implemented rules."
It does NOT mean Apple will approve the app's App Privacy declaration, and
nothing here publishes an answer to App Store Connect or mutates it in
any way -- this module only reads local project state.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ..readiness.inspector import ProjectInspector
from ..readiness.models import ReadinessReport
from ..readiness.report import build_report
from . import manifest as manifest_module
from . import sdk_catalog
from .contradictions import find_contradictions
from .inspector import inspect_local_privacy_answers, inspect_network_signals, inspect_permissions
from .mapper import build_candidates
from .models import CandidateState, Confidence, Contradiction, PrivacyCandidate, PrivacyEvidence, UserConfirmationQuestion


def _questions_for(candidates: list[PrivacyCandidate]) -> list[UserConfirmationQuestion]:
    questions: list[UserConfirmationQuestion] = []
    for candidate in candidates:
        if candidate.state is CandidateState.CONFIRMED:
            continue
        label = candidate.apple_data_type.replace("_", " ").title()
        if candidate.collection.value == "UNKNOWN":
            questions.append(UserConfirmationQuestion(
                question_id=f"question:{candidate.apple_data_type}:collection",
                data_type=candidate.apple_data_type,
                question=f"Does the app transmit {label} off the device, and is it retained beyond real-time request servicing?",
                why_needed="Local evidence proves ACCESS only; collection cannot be inferred from a permission or SDK presence alone.",
                evidence_ids=candidate.evidence_ids,
            ))
        if candidate.linked_to_user.value == "UNKNOWN":
            questions.append(UserConfirmationQuestion(
                question_id=f"question:{candidate.apple_data_type}:linked_to_user",
                data_type=candidate.apple_data_type,
                question=f"Is {label} data linked to an account, device, or identifiable user?",
                why_needed="Linkage to a user cannot be inferred from access or transmission evidence alone.",
                evidence_ids=candidate.evidence_ids,
            ))
        if candidate.tracking.value == "UNKNOWN":
            questions.append(UserConfirmationQuestion(
                question_id=f"question:{candidate.apple_data_type}:tracking",
                data_type=candidate.apple_data_type,
                question=f"Is {label} data used for tracking as defined by Apple?",
                why_needed="Tracking cannot be inferred from access, collection, or SDK presence alone.",
                evidence_ids=candidate.evidence_ids,
            ))
        if not candidate.purpose_candidates:
            questions.append(UserConfirmationQuestion(
                question_id=f"question:{candidate.apple_data_type}:purpose",
                data_type=candidate.apple_data_type,
                question=f"What purpose(s) apply to {label} data, if any is collected?",
                why_needed="No purpose evidence was found locally.",
                evidence_ids=candidate.evidence_ids,
                answer_type="MULTI_SELECT",
                allowed_answers=(
                    "APP_FUNCTIONALITY", "ANALYTICS", "DEVELOPER_ADVERTISING",
                    "THIRD_PARTY_ADVERTISING", "PRODUCT_PERSONALIZATION", "OTHER",
                ),
            ))
    return questions


def _apply_contradictions(
    candidates: list[PrivacyCandidate], contradictions: list[Contradiction],
) -> list[PrivacyCandidate]:
    by_evidence_id: dict[str, list[str]] = {}
    for item in contradictions:
        by_evidence_id.setdefault(item.evidence_left, []).append(item.contradiction_id)
        if item.evidence_right:
            by_evidence_id.setdefault(item.evidence_right, []).append(item.contradiction_id)
    updated: list[PrivacyCandidate] = []
    for candidate in candidates:
        hits = sorted({cid for eid in candidate.evidence_ids for cid in by_evidence_id.get(eid, [])})
        if hits:
            updated.append(replace(
                candidate, state=CandidateState.CONTRADICTED, contradictions=tuple(hits),
                requires_user_confirmation=True, confidence=Confidence.LOW,
            ))
        else:
            updated.append(candidate)
    return updated


@dataclass(frozen=True)
class PrivacyIntelligenceResult:
    project: str
    evidence: tuple[PrivacyEvidence, ...] | list[PrivacyEvidence] = field(default_factory=tuple)
    candidates: tuple[PrivacyCandidate, ...] | list[PrivacyCandidate] = field(default_factory=tuple)
    contradictions: tuple[Contradiction, ...] | list[Contradiction] = field(default_factory=tuple)
    questions: tuple[UserConfirmationQuestion, ...] | list[UserConfirmationQuestion] = field(default_factory=tuple)
    manifest_issues: tuple[dict, ...] | list[dict] = field(default_factory=tuple)
    privacy_policy_status: str = "UNKNOWN"
    privacy_policy_message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "contradictions", tuple(self.contradictions))
        object.__setattr__(self, "questions", tuple(self.questions))
        object.__setattr__(self, "manifest_issues", tuple(self.manifest_issues))

    def ordered_evidence(self) -> tuple[PrivacyEvidence, ...]:
        return tuple(sorted(self.evidence, key=lambda item: item.evidence_id))

    def ordered_candidates(self) -> tuple[PrivacyCandidate, ...]:
        return tuple(sorted(self.candidates, key=lambda item: item.candidate_id))

    def ordered_contradictions(self) -> tuple[Contradiction, ...]:
        return tuple(sorted(self.contradictions, key=lambda item: item.contradiction_id))

    def ordered_questions(self) -> tuple[UserConfirmationQuestion, ...]:
        return tuple(sorted(self.questions, key=lambda item: item.question_id))

    @property
    def counts(self) -> dict[str, int]:
        return {
            "permission_evidence": sum(1 for item in self.evidence if item.kind == "permission_declaration"),
            "privacy_manifests": sum(1 for item in self.evidence if item.source_type == "PrivacyInfo.xcprivacy"),
            "sdk_signals": sum(1 for item in self.evidence if item.kind == "sdk_dependency"),
            "network_signals": sum(1 for item in self.evidence if item.kind.startswith("network_")),
            "contradictions": len(self.contradictions),
            "user_confirmations": len(self.questions),
        }

    @property
    def has_blocking_manifest_issue(self) -> bool:
        return any(issue.get("severity") == "HIGH" for issue in self.manifest_issues)

    @property
    def has_unresolved_facts(self) -> bool:
        if not self.evidence:
            return True
        if any(candidate.requires_user_confirmation for candidate in self.candidates):
            return True
        if any(item.requires_user_confirmation for item in self.evidence if item.data_type_candidate is None):
            return True
        if self.privacy_policy_status != "PASS":
            return True
        return False

    @property
    def gate(self) -> str:
        if self.has_blocking_manifest_issue:
            return "BLOCKED"
        if self.contradictions or self.has_unresolved_facts:
            return "CONDITIONAL"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "privacy_intelligence": self.gate,
            "privacy_evidence": [item.to_dict() for item in self.ordered_evidence()],
            "privacy_candidates": [item.to_dict() for item in self.ordered_candidates()],
            "privacy_contradictions": [item.to_dict() for item in self.ordered_contradictions()],
            "privacy_unknowns": [item.to_dict() for item in self.ordered_questions()],
            "privacy_summary": {
                "counts": self.counts,
                "manifest_issues": list(self.manifest_issues),
                "privacy_policy_status": self.privacy_policy_status,
                "gate": self.gate,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrivacyIntelligenceResult":
        summary = data.get("privacy_summary", {})
        return cls(
            project=data.get("project", ""),
            evidence=tuple(PrivacyEvidence.from_dict(item) for item in data.get("privacy_evidence", [])),
            candidates=tuple(PrivacyCandidate.from_dict(item) for item in data.get("privacy_candidates", [])),
            contradictions=tuple(Contradiction.from_dict(item) for item in data.get("privacy_contradictions", [])),
            questions=tuple(UserConfirmationQuestion.from_dict(item) for item in data.get("privacy_unknowns", [])),
            manifest_issues=tuple(summary.get("manifest_issues", [])),
            privacy_policy_status=summary.get("privacy_policy_status", "UNKNOWN"),
        )


def run_privacy_intelligence(
    project_path: str | Path, readiness_report: ReadinessReport | None = None,
) -> PrivacyIntelligenceResult:
    inspector = ProjectInspector(project_path)
    readiness_report = readiness_report or build_report(inspector.root)

    evidence: list[PrivacyEvidence] = []
    evidence.extend(inspect_permissions(inspector))
    manifest_evidence, manifest_issues = manifest_module.inspect(inspector)
    evidence.extend(manifest_evidence)
    rr_evidence, rr_issues = manifest_module.inspect_required_reason_apis(inspector, manifest_evidence)
    evidence.extend(rr_evidence)
    manifest_issues.extend(rr_issues)
    evidence.extend(sdk_catalog.inspect_dependencies(inspector))
    evidence.extend(inspect_network_signals(inspector))
    evidence.extend(inspect_local_privacy_answers(inspector))

    contradictions = find_contradictions(evidence, manifest_issues)
    candidates = _apply_contradictions(build_candidates(evidence), contradictions)
    questions = _questions_for(candidates)

    privacy_policy_finding = next(
        (item for item in readiness_report.findings if item.finding_id == "metadata.privacy_policy"), None,
    )
    privacy_policy_status = privacy_policy_finding.status.value if privacy_policy_finding else "UNKNOWN"
    privacy_policy_message = (
        privacy_policy_finding.message if privacy_policy_finding else "Privacy policy URL was not evaluated."
    )

    return PrivacyIntelligenceResult(
        project=str(inspector.root),
        evidence=tuple(evidence),
        candidates=tuple(candidates),
        contradictions=tuple(contradictions),
        questions=tuple(questions),
        manifest_issues=tuple(issue.to_dict() for issue in manifest_issues),
        privacy_policy_status=privacy_policy_status,
        privacy_policy_message=privacy_policy_message,
    )


def human_summary(result: PrivacyIntelligenceResult) -> str:
    counts = result.counts
    lines = [
        "=== APP PRIVACY INTELLIGENCE ===",
        "",
        f"{'PERMISSION EVIDENCE':<26}{counts['permission_evidence']}",
        f"{'PRIVACY MANIFESTS':<26}{counts['privacy_manifests']}",
        f"{'SDK SIGNALS':<26}{counts['sdk_signals']}",
        f"{'NETWORK SIGNALS':<26}{counts['network_signals']}",
        f"{'CONTRADICTIONS':<26}{counts['contradictions']}",
        f"{'USER CONFIRMATIONS':<26}{counts['user_confirmations']}",
        "",
        "PRIVACY_GATE:",
        result.gate,
        "",
        "This does not mean Apple will approve the App Privacy declaration; it means",
        "no blocking structural defect and no unresolved fact was found by the",
        "currently implemented rules. Nothing here publishes an answer to App Store",
        "Connect.",
        "",
        "=== END APP PRIVACY INTELLIGENCE ===",
    ]
    return "\n".join(lines)
