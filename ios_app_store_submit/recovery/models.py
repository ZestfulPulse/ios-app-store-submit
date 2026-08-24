"""Stable data contracts for Phase 6 (Rejection Recovery).

Reuses ``review.models.Confidence`` and ``readiness.models.Evidence`` so
evidence/confidence mean the same thing everywhere in this codebase.

Hard invariants enforced at construction time:

1. A RootCauseCandidate may not be CONFIRMED without evidence (mirrors the
   BLOCKED-requires-evidence rule used by every earlier phase).
2. A Claim's displayed statement is derived FROM its ClaimStatus by a fixed
   template, never supplied as free text by a caller -- so an UNVERIFIED
   claim cannot be phrased as "fixed" even by construction error. This is a
   structural claim gate, not a text-scan after the fact (a text-scan test
   exists too, as a second, independent line of defense).
3. ReplyDraft.ready_to_send is derived, never set directly by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..readiness.models import Evidence
from ..review.models import Confidence

__all__ = [
    "Confidence", "Evidence", "RejectionSource", "RootCauseCategory", "RootCauseStatus",
    "Safety", "ClaimStatus", "ResponseMode", "RejectionMessage", "RuleMapping",
    "RootCauseCandidate", "RecoveryFixPlan", "Claim", "ReplyDraft", "VerificationResult",
]


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class RejectionSource(_StringEnum):
    MANUAL_TEXT = "MANUAL_TEXT"
    ASC_EXPORT = "ASC_EXPORT"
    LOCAL_FIXTURE = "LOCAL_FIXTURE"


class RootCauseCategory(_StringEnum):
    TECHNICAL = "TECHNICAL"
    PERFORMANCE = "PERFORMANCE"
    METADATA = "METADATA"
    PRIVACY = "PRIVACY"
    REVIEW_ACCESS = "REVIEW_ACCESS"
    DESIGN_HIG = "DESIGN_HIG"
    LOCALIZATION = "LOCALIZATION"
    SCREENSHOT_ASSET = "SCREENSHOT_ASSET"
    PAYMENTS_IAP = "PAYMENTS_IAP"
    LEGAL_POLICY = "LEGAL_POLICY"
    UNKNOWN = "UNKNOWN"


class RootCauseStatus(_StringEnum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"


class Safety(_StringEnum):
    SAFE = "SAFE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    MANUAL = "MANUAL"
    FORBIDDEN = "FORBIDDEN"


class ClaimStatus(_StringEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    USER_ATTESTED = "USER_ATTESTED"
    FORBIDDEN_TO_CLAIM = "FORBIDDEN_TO_CLAIM"


class ResponseMode(_StringEnum):
    FIXED = "FIXED"
    PARTIALLY_FIXED = "PARTIALLY_FIXED"
    CLARIFICATION = "CLARIFICATION"
    DISPUTE_WITH_EVIDENCE = "DISPUTE_WITH_EVIDENCE"


@dataclass(frozen=True)
class RejectionMessage:
    rejection_id: str
    source: RejectionSource | str
    received_at: str
    raw_text: str
    guideline_refs: tuple[str, ...] | list[str] = field(default_factory=tuple)
    review_state: str = "REJECTED"
    attachments: tuple[str, ...] | list[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", RejectionSource(self.source))
        object.__setattr__(self, "guideline_refs", tuple(self.guideline_refs))
        object.__setattr__(self, "attachments", tuple(self.attachments))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejection_id": self.rejection_id,
            "source": self.source.value,
            "received_at": self.received_at,
            "raw_text": self.raw_text,
            "guideline_refs": list(self.guideline_refs),
            "review_state": self.review_state,
            "attachments": list(self.attachments),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RejectionMessage":
        return cls(
            rejection_id=data["rejection_id"], source=data["source"], received_at=data["received_at"],
            raw_text=data["raw_text"], guideline_refs=tuple(data.get("guideline_refs", [])),
            review_state=data.get("review_state", "REJECTED"), attachments=tuple(data.get("attachments", [])),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class RuleMapping:
    mapping_id: str
    rejection_id: str
    apple_guideline: str | None
    mapped_rule_ids: tuple[str, ...] | list[str]
    category: RootCauseCategory | str
    confidence: Confidence | str
    evidence: tuple[Evidence, ...] | list[Evidence]
    mapping_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapped_rule_ids", tuple(self.mapped_rule_ids))
        object.__setattr__(self, "category", RootCauseCategory(self.category))
        object.__setattr__(self, "confidence", Confidence(self.confidence))
        object.__setattr__(self, "evidence", tuple(
            item if isinstance(item, Evidence) else Evidence.from_dict(item) for item in self.evidence
        ))
        if not self.mapped_rule_ids and self.confidence is Confidence.HIGH:
            raise ValueError(f"{self.mapping_id}: a mapping with no matched rule id may not be HIGH confidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "rejection_id": self.rejection_id,
            "apple_guideline": self.apple_guideline,
            "mapped_rule_ids": list(self.mapped_rule_ids),
            "category": self.category.value,
            "confidence": self.confidence.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "mapping_reason": self.mapping_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuleMapping":
        return cls(
            mapping_id=data["mapping_id"], rejection_id=data["rejection_id"],
            apple_guideline=data.get("apple_guideline"), mapped_rule_ids=tuple(data.get("mapped_rule_ids", [])),
            category=data["category"], confidence=data["confidence"],
            evidence=tuple(Evidence.from_dict(item) for item in data.get("evidence", [])),
            mapping_reason=data["mapping_reason"],
        )


@dataclass(frozen=True)
class RootCauseCandidate:
    root_cause_id: str
    rejection_id: str
    category: RootCauseCategory | str
    title: str
    hypothesis: str
    confidence: Confidence | str
    evidence: tuple[Evidence, ...] | list[Evidence]
    missing_evidence: tuple[str, ...] | list[str]
    related_findings: tuple[str, ...] | list[str]
    source_paths: tuple[str, ...] | list[str]
    requires_runtime: bool
    requires_user_confirmation: bool
    status: RootCauseStatus | str

    def __post_init__(self) -> None:
        status = RootCauseStatus(self.status)
        evidence = tuple(
            item if isinstance(item, Evidence) else Evidence.from_dict(item) for item in self.evidence
        )
        if status is RootCauseStatus.CONFIRMED and not evidence:
            raise ValueError(f"{self.root_cause_id}: CONFIRMED requires deterministic evidence")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "category", RootCauseCategory(self.category))
        object.__setattr__(self, "confidence", Confidence(self.confidence))
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "missing_evidence", tuple(self.missing_evidence))
        object.__setattr__(self, "related_findings", tuple(self.related_findings))
        object.__setattr__(self, "source_paths", tuple(self.source_paths))

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_cause_id": self.root_cause_id,
            "rejection_id": self.rejection_id,
            "category": self.category.value,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "confidence": self.confidence.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "missing_evidence": list(self.missing_evidence),
            "related_findings": list(self.related_findings),
            "source_paths": list(self.source_paths),
            "requires_runtime": self.requires_runtime,
            "requires_user_confirmation": self.requires_user_confirmation,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RootCauseCandidate":
        return cls(
            root_cause_id=data["root_cause_id"], rejection_id=data["rejection_id"], category=data["category"],
            title=data["title"], hypothesis=data["hypothesis"], confidence=data["confidence"],
            evidence=tuple(Evidence.from_dict(item) for item in data.get("evidence", [])),
            missing_evidence=tuple(data.get("missing_evidence", [])),
            related_findings=tuple(data.get("related_findings", [])),
            source_paths=tuple(data.get("source_paths", [])),
            requires_runtime=data.get("requires_runtime", False),
            requires_user_confirmation=data.get("requires_user_confirmation", False),
            status=data["status"],
        )


@dataclass(frozen=True)
class RecoveryFixPlan:
    fix_id: str
    root_cause_id: str
    finding_ids: tuple[str, ...] | list[str]
    safety: Safety | str
    title: str
    description: str
    target_paths: tuple[str, ...] | list[str]
    proposed_changes: str
    verification_plan: str
    reply_claim_allowed: bool
    requires_user_approval: bool
    status: str = "PLANNED"

    def __post_init__(self) -> None:
        safety = Safety(self.safety)
        if safety in (Safety.FORBIDDEN, Safety.MANUAL, Safety.APPROVAL_REQUIRED) and not self.requires_user_approval:
            raise ValueError(f"{self.fix_id}: {safety.value} plans must require user approval")
        object.__setattr__(self, "safety", safety)
        object.__setattr__(self, "finding_ids", tuple(self.finding_ids))
        object.__setattr__(self, "target_paths", tuple(self.target_paths))

    def to_dict(self) -> dict[str, Any]:
        return {
            "fix_id": self.fix_id,
            "root_cause_id": self.root_cause_id,
            "finding_ids": list(self.finding_ids),
            "safety": self.safety.value,
            "title": self.title,
            "description": self.description,
            "target_paths": list(self.target_paths),
            "proposed_changes": self.proposed_changes,
            "verification_plan": self.verification_plan,
            "reply_claim_allowed": self.reply_claim_allowed,
            "requires_user_approval": self.requires_user_approval,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecoveryFixPlan":
        return cls(
            fix_id=data["fix_id"], root_cause_id=data["root_cause_id"],
            finding_ids=tuple(data.get("finding_ids", [])), safety=data["safety"], title=data["title"],
            description=data["description"], target_paths=tuple(data.get("target_paths", [])),
            proposed_changes=data["proposed_changes"], verification_plan=data["verification_plan"],
            reply_claim_allowed=data.get("reply_claim_allowed", False),
            requires_user_approval=data.get("requires_user_approval", True), status=data.get("status", "PLANNED"),
        )


# Claim wording is a fixed function of (kind, status) -- never free text
# supplied by a caller. This is the structural half of the claim gate.
_CLAIM_TEMPLATES = {
    ("fix", ClaimStatus.VERIFIED): "We have fixed and verified {subject}.",
    ("fix", ClaimStatus.USER_ATTESTED): "We have addressed {subject}; the developer has confirmed this directly.",
    ("fix", ClaimStatus.UNVERIFIED): "We investigated {subject} and have prepared a proposed change.",
    ("fix", ClaimStatus.FORBIDDEN_TO_CLAIM): "We are unable to confirm {subject} without additional information.",
    ("dispute", ClaimStatus.VERIFIED): "Our review of {subject} found it already satisfies the cited guideline.",
    ("dispute", ClaimStatus.USER_ATTESTED): "The developer confirms {subject} already satisfies the cited guideline.",
    ("dispute", ClaimStatus.UNVERIFIED): "We would like to understand more about {subject} before proposing a change.",
    ("dispute", ClaimStatus.FORBIDDEN_TO_CLAIM): "We are unable to confirm {subject} without additional information.",
    ("clarification", ClaimStatus.VERIFIED): "We investigated {subject} and would appreciate confirmation this resolves it.",
    ("clarification", ClaimStatus.USER_ATTESTED): "We investigated {subject} and would appreciate confirmation this resolves it.",
    ("clarification", ClaimStatus.UNVERIFIED): "We would appreciate clarification regarding {subject}.",
    ("clarification", ClaimStatus.FORBIDDEN_TO_CLAIM): "We are unable to confirm {subject} without additional information.",
}


@dataclass(frozen=True)
class Claim:
    claim_id: str
    subject: str
    kind: str
    status: ClaimStatus | str
    evidence_refs: tuple[str, ...] | list[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.kind not in ("fix", "dispute", "clarification"):
            raise ValueError(f"{self.claim_id}: unknown claim kind {self.kind!r}")
        object.__setattr__(self, "status", ClaimStatus(self.status))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    @property
    def statement(self) -> str:
        template = _CLAIM_TEMPLATES[(self.kind, self.status)]
        return template.format(subject=self.subject)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "subject": self.subject,
            "kind": self.kind,
            "status": self.status.value,
            "evidence_refs": list(self.evidence_refs),
            "statement": self.statement,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Claim":
        return cls(
            claim_id=data["claim_id"], subject=data["subject"], kind=data["kind"], status=data["status"],
            evidence_refs=tuple(data.get("evidence_refs", [])),
        )


@dataclass(frozen=True)
class ReplyDraft:
    draft_id: str
    rejection_id: str
    language: str
    subject: str
    body: str
    claims: tuple[Claim, ...] | list[Claim]
    response_mode: ResponseMode | str
    evidence_refs: tuple[str, ...] | list[str]
    requires_user_review: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "claims", tuple(self.claims))
        object.__setattr__(self, "response_mode", ResponseMode(self.response_mode))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    @property
    def claim_statuses(self) -> tuple[str, ...]:
        return tuple(claim.status.value for claim in self.claims)

    @property
    def ready_to_send(self) -> bool:
        if any(claim.status is ClaimStatus.FORBIDDEN_TO_CLAIM for claim in self.claims):
            return False
        if any(claim.status is ClaimStatus.UNVERIFIED for claim in self.claims):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "rejection_id": self.rejection_id,
            "language": self.language,
            "subject": self.subject,
            "body": self.body,
            "claims": [item.to_dict() for item in self.claims],
            "claim_statuses": list(self.claim_statuses),
            "response_mode": self.response_mode.value,
            "evidence_refs": list(self.evidence_refs),
            "requires_user_review": self.requires_user_review,
            "ready_to_send": self.ready_to_send,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReplyDraft":
        return cls(
            draft_id=data["draft_id"], rejection_id=data["rejection_id"], language=data["language"],
            subject=data["subject"], body=data["body"],
            claims=tuple(Claim.from_dict(item) for item in data.get("claims", [])),
            response_mode=data["response_mode"], evidence_refs=tuple(data.get("evidence_refs", [])),
            requires_user_review=data.get("requires_user_review", True),
        )


@dataclass(frozen=True)
class VerificationResult:
    verification_id: str
    root_cause_id: str
    claim_status: ClaimStatus | str
    pending_reason: str | None
    rechecked_rule_ids: tuple[str, ...] | list[str]
    message: str
    evidence: tuple[Evidence, ...] | list[Evidence]

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_status", ClaimStatus(self.claim_status))
        object.__setattr__(self, "rechecked_rule_ids", tuple(self.rechecked_rule_ids))
        object.__setattr__(self, "evidence", tuple(
            item if isinstance(item, Evidence) else Evidence.from_dict(item) for item in self.evidence
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "root_cause_id": self.root_cause_id,
            "claim_status": self.claim_status.value,
            "pending_reason": self.pending_reason,
            "rechecked_rule_ids": list(self.rechecked_rule_ids),
            "message": self.message,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerificationResult":
        return cls(
            verification_id=data["verification_id"], root_cause_id=data["root_cause_id"],
            claim_status=data["claim_status"], pending_reason=data.get("pending_reason"),
            rechecked_rule_ids=tuple(data.get("rechecked_rule_ids", [])), message=data["message"],
            evidence=tuple(Evidence.from_dict(item) for item in data.get("evidence", [])),
        )
