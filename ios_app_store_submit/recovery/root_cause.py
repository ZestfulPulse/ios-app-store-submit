"""Turn rule mappings into root-cause hypotheses against local evidence.

A root cause is only ever CONFIRMED when Phase 3/4/5's own category rollup
deterministically corroborates Apple's claim (the same engines those
phases already use to decide BLOCKED/PASS). Static source inspection alone
can never confirm a runtime claim like a crash -- those stay
UNKNOWN/POSSIBLE with requires_runtime=True.
"""

from __future__ import annotations

from ..readiness.models import Evidence
from ..review.models import Confidence
from .models import RejectionMessage, RootCauseCandidate, RootCauseCategory, RootCauseStatus, RuleMapping

CATEGORY_TITLES = {
    RootCauseCategory.TECHNICAL: "Technical stability issue",
    RootCauseCategory.PERFORMANCE: "Performance/completeness issue",
    RootCauseCategory.METADATA: "Metadata issue",
    RootCauseCategory.PRIVACY: "Privacy declaration issue",
    RootCauseCategory.REVIEW_ACCESS: "Review access issue",
    RootCauseCategory.DESIGN_HIG: "HIG design issue",
    RootCauseCategory.LOCALIZATION: "Localization issue",
    RootCauseCategory.SCREENSHOT_ASSET: "Screenshot/asset issue",
    RootCauseCategory.PAYMENTS_IAP: "Payments/IAP issue",
    RootCauseCategory.LEGAL_POLICY: "Legal/policy issue",
    RootCauseCategory.UNKNOWN: "Unclassified issue",
}

# Categories whose truth can never be established from static inspection
# alone; they always require either runtime evidence or a human decision.
_RUNTIME_REQUIRED_CATEGORIES = {RootCauseCategory.TECHNICAL}
_USER_CONFIRMATION_CATEGORIES = {
    RootCauseCategory.PAYMENTS_IAP, RootCauseCategory.LEGAL_POLICY, RootCauseCategory.SCREENSHOT_ASSET,
}

_REVIEW_CATEGORIES = {RootCauseCategory.PERFORMANCE, RootCauseCategory.METADATA, RootCauseCategory.REVIEW_ACCESS}


def _normalize(status: str | None) -> str | None:
    if status == "PASS":
        return "PASS"
    if status == "BLOCKED":
        return "BLOCKED"
    return None


def category_recheck_status(
    category: RootCauseCategory, *, pre_review_result=None, privacy_result=None, design_result=None,
) -> str | None:
    """Consult the Phase 3/4/5 engine that actually owns this category's
    verdict, rather than re-deriving it from raw readiness gates."""
    if category is RootCauseCategory.PRIVACY:
        if privacy_result is not None:
            return _normalize(privacy_result.gate)
        if pre_review_result is not None:
            return _normalize(pre_review_result.category_status.get("PRIVACY"))
        return None
    if category in _REVIEW_CATEGORIES and pre_review_result is not None:
        return _normalize(pre_review_result.category_status.get(category.value))
    if category is RootCauseCategory.DESIGN_HIG and design_result is not None:
        return _normalize(design_result.gate)
    if category is RootCauseCategory.LOCALIZATION and design_result is not None:
        return _normalize(design_result.area_status.get("LOCALIZATION"))
    return None


def _related_findings_and_evidence(
    category: RootCauseCategory, *, pre_review_result=None, privacy_result=None, design_result=None,
) -> tuple[tuple[str, ...], tuple[Evidence, ...]]:
    if category in _REVIEW_CATEGORIES | {RootCauseCategory.PRIVACY} and pre_review_result is not None:
        matches = [f for f in pre_review_result.ordered_findings() if f.category == category.value]
        if matches:
            worst = [f for f in matches if f.status.value == "BLOCKED"] or matches
            evidence = tuple(item for finding in worst[:3] for item in finding.evidence[:2])
            return tuple(f.finding_id for f in matches), evidence
    if category is RootCauseCategory.DESIGN_HIG and design_result is not None:
        matches = [f for f in design_result.ordered_findings() if f.hig_area != "LOCALIZATION"]
        worst = [f for f in matches if f.status.value == "BLOCKED"] or matches
        evidence = tuple(Evidence(kind=item.kind, path=item.source_path, observed=item.observed, source="design")
                          for finding in worst[:3] for item in finding.evidence[:2])
        return tuple(f.finding_id for f in matches), evidence
    if category is RootCauseCategory.LOCALIZATION and design_result is not None:
        matches = [f for f in design_result.ordered_findings() if f.hig_area == "LOCALIZATION"]
        worst = [f for f in matches if f.status.value == "BLOCKED"] or matches
        evidence = tuple(Evidence(kind=item.kind, path=item.source_path, observed=item.observed, source="design")
                          for finding in worst[:3] for item in finding.evidence[:2])
        return tuple(f.finding_id for f in matches), evidence
    return (), ()


def _crash_root_cause(rejection: RejectionMessage, category_evidence: tuple[Evidence, ...]) -> RootCauseCandidate:
    return RootCauseCandidate(
        root_cause_id=f"root_cause:{rejection.rejection_id}:TECHNICAL",
        rejection_id=rejection.rejection_id, category=RootCauseCategory.TECHNICAL,
        title=CATEGORY_TITLES[RootCauseCategory.TECHNICAL],
        hypothesis="Apple reported a crash/hang/performance failure. Static source inspection alone cannot "
                   "confirm or reproduce a runtime crash.",
        confidence=Confidence.LOW, evidence=category_evidence,
        missing_evidence=("device/simulator crash log or reproduction evidence",),
        related_findings=(), source_paths=(), requires_runtime=True, requires_user_confirmation=False,
        status=RootCauseStatus.UNKNOWN,
    )


def _category_root_cause(
    rejection: RejectionMessage, category: RootCauseCategory, category_evidence: tuple[Evidence, ...],
    *, high_confidence: bool, pre_review_result=None, privacy_result=None, design_result=None,
) -> RootCauseCandidate:
    recheck = category_recheck_status(
        category, pre_review_result=pre_review_result, privacy_result=privacy_result, design_result=design_result,
    )
    related, local_evidence = _related_findings_and_evidence(
        category, pre_review_result=pre_review_result, privacy_result=privacy_result, design_result=design_result,
    )
    evidence = category_evidence + local_evidence
    requires_runtime = category in _RUNTIME_REQUIRED_CATEGORIES
    requires_user_confirmation = category in _USER_CONFIRMATION_CATEGORIES

    if recheck == "BLOCKED":
        return RootCauseCandidate(
            root_cause_id=f"root_cause:{rejection.rejection_id}:{category.value}",
            rejection_id=rejection.rejection_id, category=category, title=CATEGORY_TITLES[category],
            hypothesis=f"Apple's concern is corroborated by a local, deterministic {category.value.lower()} finding.",
            confidence=Confidence.HIGH, evidence=evidence, missing_evidence=(), related_findings=related,
            source_paths=(), requires_runtime=False, requires_user_confirmation=False,
            status=RootCauseStatus.CONFIRMED,
        )
    if recheck == "PASS":
        status = RootCauseStatus.CONTRADICTED if high_confidence else RootCauseStatus.LIKELY
        return RootCauseCandidate(
            root_cause_id=f"root_cause:{rejection.rejection_id}:{category.value}",
            rejection_id=rejection.rejection_id, category=category, title=CATEGORY_TITLES[category],
            hypothesis=f"Apple raised a {category.value.lower()} concern, but the local {category.value.lower()} "
                       "check currently shows no issue.",
            confidence=Confidence.MEDIUM, evidence=evidence,
            missing_evidence=("confirmation Apple's specific concern matches what was locally checked",),
            related_findings=related, source_paths=(), requires_runtime=requires_runtime,
            requires_user_confirmation=True, status=status,
        )
    return RootCauseCandidate(
        root_cause_id=f"root_cause:{rejection.rejection_id}:{category.value}",
        rejection_id=rejection.rejection_id, category=category, title=CATEGORY_TITLES[category],
        hypothesis=f"Apple raised a {category.value.lower()} concern; local evidence is insufficient to "
                   "confirm or refute it from source alone.",
        confidence=Confidence.LOW, evidence=evidence, missing_evidence=("local evidence for this category",),
        related_findings=related, source_paths=(), requires_runtime=requires_runtime,
        requires_user_confirmation=requires_user_confirmation, status=RootCauseStatus.UNKNOWN,
    )


_CONFIDENCE_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def analyze_root_causes(
    rejection: RejectionMessage, mappings: list[RuleMapping], *, pre_review_result=None, privacy_result=None,
    design_result=None,
) -> list[RootCauseCandidate]:
    categories: dict[RootCauseCategory, list[Evidence]] = {}
    category_confidence: dict[RootCauseCategory, Confidence] = {}
    for mapping in mappings:
        if mapping.category is RootCauseCategory.UNKNOWN and len(mappings) > 1:
            continue
        categories.setdefault(mapping.category, []).extend(mapping.evidence)
        current = category_confidence.get(mapping.category)
        if current is None or _CONFIDENCE_RANK[mapping.confidence] > _CONFIDENCE_RANK[current]:
            category_confidence[mapping.category] = mapping.confidence

    if not categories:
        categories[RootCauseCategory.UNKNOWN] = []

    root_causes: list[RootCauseCandidate] = []
    for category in sorted(categories, key=lambda item: item.value):
        evidence = tuple(categories[category])
        high_confidence = category_confidence.get(category) is Confidence.HIGH
        if category is RootCauseCategory.TECHNICAL and any(
            "crash" in str(item.observed).lower() or "hang" in str(item.observed).lower()
            or "unresponsive" in str(item.observed).lower() for item in evidence
        ):
            root_causes.append(_crash_root_cause(rejection, evidence))
        elif category is RootCauseCategory.UNKNOWN:
            root_causes.append(RootCauseCandidate(
                root_cause_id=f"root_cause:{rejection.rejection_id}:UNKNOWN",
                rejection_id=rejection.rejection_id, category=RootCauseCategory.UNKNOWN,
                title=CATEGORY_TITLES[RootCauseCategory.UNKNOWN],
                hypothesis="The rejection text did not contain an explicit guideline number or a recognized "
                           "signal keyword; the concern cannot be classified from text alone.",
                confidence=Confidence.LOW, evidence=evidence,
                missing_evidence=("a more specific rejection text or an explicit guideline number",),
                related_findings=(), source_paths=(), requires_runtime=False, requires_user_confirmation=True,
                status=RootCauseStatus.UNKNOWN,
            ))
        else:
            root_causes.append(_category_root_cause(
                rejection, category, evidence, high_confidence=high_confidence,
                pre_review_result=pre_review_result, privacy_result=privacy_result, design_result=design_result,
            ))
    return root_causes
