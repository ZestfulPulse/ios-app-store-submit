"""Stable data contracts for Phase 4 (Privacy Intelligence).

Apple Privacy semantics are modelled as five independent tri-state facts --
ACCESS, TRANSMISSION, COLLECTION, LINKED_TO_USER, TRACKING -- plus a set of
possible PURPOSE candidates. None of these facts may be collapsed into one
another: a permission declaration proves ACCESS only, and must never be
read as proof of COLLECTION, LINKED_TO_USER, TRACKING, or PURPOSE.

Tri-state fields default to UNKNOWN. Absence of evidence is UNKNOWN, never
NO -- NO is reserved for an explicit, attributable statement that a fact
does not hold (e.g. a developer's own local App Privacy answer, or a
manifest entry that explicitly says so). Nothing in this package publishes
App Privacy answers or mutates App Store Connect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..review.models import Confidence, confidence_from_float

__all__ = [
    "Confidence", "confidence_from_float", "TriState", "tri_state", "Purpose", "CandidateState",
    "Severity", "PrivacyEvidence", "PrivacyCandidate", "Contradiction", "UserConfirmationQuestion",
]


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class TriState(_StringEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


def tri_state(value: Any) -> TriState:
    if isinstance(value, TriState):
        return value
    if value is None:
        return TriState.UNKNOWN
    if isinstance(value, bool):
        return TriState.YES if value else TriState.NO
    return TriState(str(value).upper())


class Purpose(_StringEnum):
    APP_FUNCTIONALITY = "APP_FUNCTIONALITY"
    ANALYTICS = "ANALYTICS"
    DEVELOPER_ADVERTISING = "DEVELOPER_ADVERTISING"
    THIRD_PARTY_ADVERTISING = "THIRD_PARTY_ADVERTISING"
    PRODUCT_PERSONALIZATION = "PRODUCT_PERSONALIZATION"
    OTHER = "OTHER"


class CandidateState(_StringEnum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"


class Severity(_StringEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class PrivacyEvidence:
    evidence_id: str
    kind: str
    source_type: str
    observed: Any = None
    source_path: str | None = None
    data_type_candidate: str | None = None
    access: TriState | str = TriState.UNKNOWN
    transmission: TriState | str = TriState.UNKNOWN
    collection: TriState | str = TriState.UNKNOWN
    linked_to_user: TriState | str = TriState.UNKNOWN
    tracking: TriState | str = TriState.UNKNOWN
    purpose_candidates: tuple[str, ...] | list[str] = field(default_factory=tuple)
    confidence: Confidence | str = Confidence.LOW
    requires_user_confirmation: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "access", tri_state(self.access))
        object.__setattr__(self, "transmission", tri_state(self.transmission))
        object.__setattr__(self, "collection", tri_state(self.collection))
        object.__setattr__(self, "linked_to_user", tri_state(self.linked_to_user))
        object.__setattr__(self, "tracking", tri_state(self.tracking))
        object.__setattr__(self, "confidence", Confidence(self.confidence))
        object.__setattr__(self, "purpose_candidates", tuple(self.purpose_candidates))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "source_type": self.source_type,
            "observed": self.observed,
            "source_path": self.source_path,
            "data_type_candidate": self.data_type_candidate,
            "access": self.access.value,
            "transmission": self.transmission.value,
            "collection": self.collection.value,
            "linked_to_user": self.linked_to_user.value,
            "tracking": self.tracking.value,
            "purpose_candidates": list(self.purpose_candidates),
            "confidence": self.confidence.value,
            "requires_user_confirmation": self.requires_user_confirmation,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PrivacyEvidence":
        return cls(
            evidence_id=data["evidence_id"], kind=data["kind"], source_type=data["source_type"],
            observed=data.get("observed"), source_path=data.get("source_path"),
            data_type_candidate=data.get("data_type_candidate"),
            access=data.get("access", TriState.UNKNOWN), transmission=data.get("transmission", TriState.UNKNOWN),
            collection=data.get("collection", TriState.UNKNOWN),
            linked_to_user=data.get("linked_to_user", TriState.UNKNOWN),
            tracking=data.get("tracking", TriState.UNKNOWN),
            purpose_candidates=tuple(data.get("purpose_candidates", [])),
            confidence=data.get("confidence", Confidence.LOW),
            requires_user_confirmation=data.get("requires_user_confirmation", True),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class PrivacyCandidate:
    candidate_id: str
    apple_data_type: str
    state: CandidateState | str
    collection: TriState | str = TriState.UNKNOWN
    linked_to_user: TriState | str = TriState.UNKNOWN
    tracking: TriState | str = TriState.UNKNOWN
    purpose_candidates: tuple[str, ...] | list[str] = field(default_factory=tuple)
    confidence: Confidence | str = Confidence.LOW
    evidence_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    contradictions: tuple[str, ...] | list[str] = field(default_factory=tuple)
    requires_user_confirmation: bool = True
    recommended_action: str = ""

    def __post_init__(self) -> None:
        state = CandidateState(self.state)
        confidence = Confidence(self.confidence)
        if state is CandidateState.CONFIRMED and confidence is not Confidence.HIGH:
            raise ValueError(
                f"{self.candidate_id}: CONFIRMED requires HIGH confidence -- only deterministic "
                "evidence may produce a CONFIRMED candidate."
            )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "collection", tri_state(self.collection))
        object.__setattr__(self, "linked_to_user", tri_state(self.linked_to_user))
        object.__setattr__(self, "tracking", tri_state(self.tracking))
        object.__setattr__(self, "purpose_candidates", tuple(self.purpose_candidates))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "contradictions", tuple(self.contradictions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "apple_data_type": self.apple_data_type,
            "state": self.state.value,
            "collection": self.collection.value,
            "linked_to_user": self.linked_to_user.value,
            "tracking": self.tracking.value,
            "purpose_candidates": list(self.purpose_candidates),
            "confidence": self.confidence.value,
            "evidence_ids": list(self.evidence_ids),
            "contradictions": list(self.contradictions),
            "requires_user_confirmation": self.requires_user_confirmation,
            "recommended_action": self.recommended_action,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PrivacyCandidate":
        return cls(
            candidate_id=data["candidate_id"], apple_data_type=data["apple_data_type"], state=data["state"],
            collection=data.get("collection", TriState.UNKNOWN),
            linked_to_user=data.get("linked_to_user", TriState.UNKNOWN),
            tracking=data.get("tracking", TriState.UNKNOWN),
            purpose_candidates=tuple(data.get("purpose_candidates", [])),
            confidence=data.get("confidence", Confidence.LOW),
            evidence_ids=tuple(data.get("evidence_ids", [])),
            contradictions=tuple(data.get("contradictions", [])),
            requires_user_confirmation=data.get("requires_user_confirmation", True),
            recommended_action=data.get("recommended_action", ""),
        )


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    kind: str
    severity: Severity | str
    evidence_left: str
    evidence_right: str | None
    message: str
    requested_resolution: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", Severity(self.severity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "kind": self.kind,
            "severity": self.severity.value,
            "evidence_left": self.evidence_left,
            "evidence_right": self.evidence_right,
            "message": self.message,
            "requested_resolution": self.requested_resolution,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Contradiction":
        return cls(
            contradiction_id=data["contradiction_id"], kind=data["kind"], severity=data["severity"],
            evidence_left=data["evidence_left"], evidence_right=data.get("evidence_right"),
            message=data["message"], requested_resolution=data["requested_resolution"],
        )


@dataclass(frozen=True)
class UserConfirmationQuestion:
    question_id: str
    data_type: str | None
    question: str
    why_needed: str
    evidence_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    answer_type: str = "TRI_STATE"
    allowed_answers: tuple[str, ...] | list[str] = field(
        default_factory=lambda: (TriState.YES.value, TriState.NO.value, TriState.UNKNOWN.value)
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "allowed_answers", tuple(self.allowed_answers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "data_type": self.data_type,
            "question": self.question,
            "why_needed": self.why_needed,
            "evidence_ids": list(self.evidence_ids),
            "answer_type": self.answer_type,
            "allowed_answers": list(self.allowed_answers),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UserConfirmationQuestion":
        return cls(
            question_id=data["question_id"], data_type=data.get("data_type"), question=data["question"],
            why_needed=data["why_needed"], evidence_ids=tuple(data.get("evidence_ids", [])),
            answer_type=data.get("answer_type", "TRI_STATE"),
            allowed_answers=tuple(data.get("allowed_answers", [])),
        )
