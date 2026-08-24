"""Map a parsed rejection onto the existing Phase 3/4/5 rule registries.

An explicit guideline number only ever produces a HIGH-confidence mapping
when a matching normalized rule actually exists in the Phase 3 registry; an
unmatched guideline number is never silently coerced to the nearest known
rule. A keyword-only (no explicit guideline number) signal is capped at
MEDIUM confidence, since text-similarity alone is never proof.
"""

from __future__ import annotations

from ..design.models import Ruleset as DesignRuleset
from ..design.models import load_ruleset as load_design_ruleset
from ..readiness.models import Evidence
from ..review.models import Confidence, Ruleset as ReviewRuleset
from ..review.registry import load_ruleset as load_review_ruleset
from .models import RejectionMessage, RootCauseCategory, RuleMapping

# Keyword signal category -> RootCauseCategory. Order matters only for
# deterministic iteration; every category maps to exactly one bucket.
SIGNAL_CATEGORY_MAP: dict[str, RootCauseCategory] = {
    "review_access": RootCauseCategory.REVIEW_ACCESS,
    "privacy": RootCauseCategory.PRIVACY,
    "metadata_refs": RootCauseCategory.METADATA,
    "crash_performance": RootCauseCategory.TECHNICAL,
    "design_hig": RootCauseCategory.DESIGN_HIG,
    "localization": RootCauseCategory.LOCALIZATION,
    "screenshot": RootCauseCategory.SCREENSHOT_ASSET,
    "payments_iap": RootCauseCategory.PAYMENTS_IAP,
    "legal_policy": RootCauseCategory.LEGAL_POLICY,
}


def _guideline_component_matches(apple_guideline: str, guideline_ref: str) -> bool:
    components = {part.strip() for part in apple_guideline.split(",")}
    return guideline_ref in components


def _map_guideline_ref(
    rejection: RejectionMessage, guideline_ref: str, review_ruleset: ReviewRuleset, index: int,
) -> RuleMapping:
    matches = [rule for rule in review_ruleset.rules if _guideline_component_matches(rule.apple_guideline, guideline_ref)]
    evidence = (Evidence(kind="text", observed=f"Guideline {guideline_ref}", source="rejection_text"),)
    if matches:
        categories = {rule.category for rule in matches}
        category = next(iter(categories)) if len(categories) == 1 else RootCauseCategory.UNKNOWN.value
        return RuleMapping(
            mapping_id=f"mapping:{rejection.rejection_id}:guideline:{guideline_ref}",
            rejection_id=rejection.rejection_id, apple_guideline=guideline_ref,
            mapped_rule_ids=tuple(rule.rule_id for rule in matches), category=category,
            confidence=Confidence.HIGH, evidence=evidence,
            mapping_reason=f"Explicit guideline {guideline_ref} matched {len(matches)} normalized rule(s).",
        )
    return RuleMapping(
        mapping_id=f"mapping:{rejection.rejection_id}:guideline:{guideline_ref}",
        rejection_id=rejection.rejection_id, apple_guideline=guideline_ref, mapped_rule_ids=(),
        category=RootCauseCategory.UNKNOWN, confidence=Confidence.LOW, evidence=evidence,
        mapping_reason=f"Guideline {guideline_ref} was cited but no normalized rule matches it; "
                       "never coerced to the nearest known rule.",
    )


def _map_signal(
    rejection: RejectionMessage, signal_category: str, keywords: list[str], *,
    review_ruleset: ReviewRuleset, design_ruleset: DesignRuleset, index: int,
) -> RuleMapping:
    category = SIGNAL_CATEGORY_MAP[signal_category]
    evidence = tuple(Evidence(kind="text", observed=keyword, source="rejection_text") for keyword in keywords)
    mapped_rule_ids: tuple[str, ...] = ()
    if category is RootCauseCategory.PRIVACY:
        mapped_rule_ids = tuple(rule.rule_id for rule in review_ruleset.rules_by_category("PRIVACY"))
    elif category is RootCauseCategory.DESIGN_HIG:
        mapped_rule_ids = tuple(rule.rule_id for rule in design_ruleset.rules)
    elif category is RootCauseCategory.REVIEW_ACCESS:
        mapped_rule_ids = tuple(rule.rule_id for rule in review_ruleset.rules_by_category("REVIEW_ACCESS"))
    elif category is RootCauseCategory.METADATA:
        mapped_rule_ids = tuple(rule.rule_id for rule in review_ruleset.rules_by_category("METADATA"))
    elif category is RootCauseCategory.LOCALIZATION:
        mapped_rule_ids = tuple(rule.rule_id for rule in design_ruleset.rules_by_area("LOCALIZATION"))
    return RuleMapping(
        mapping_id=f"mapping:{rejection.rejection_id}:signal:{signal_category}",
        rejection_id=rejection.rejection_id, apple_guideline=None, mapped_rule_ids=mapped_rule_ids,
        category=category, confidence=Confidence.MEDIUM, evidence=evidence,
        mapping_reason=f"Keyword signal(s) {keywords!r} detected in rejection text; a keyword match alone "
                       "is never HIGH confidence.",
    )


def map_rejection(
    rejection: RejectionMessage, *, review_ruleset: ReviewRuleset | None = None,
    design_ruleset: DesignRuleset | None = None,
) -> list[RuleMapping]:
    review_ruleset = review_ruleset or load_review_ruleset()
    design_ruleset = design_ruleset or load_design_ruleset()

    mappings: list[RuleMapping] = []
    for index, guideline_ref in enumerate(rejection.guideline_refs):
        mappings.append(_map_guideline_ref(rejection, guideline_ref, review_ruleset, index))

    signals = rejection.metadata.get("signals", {})
    for index, (signal_category, keywords) in enumerate(sorted(signals.items())):
        if signal_category not in SIGNAL_CATEGORY_MAP:
            continue
        mappings.append(_map_signal(
            rejection, signal_category, keywords, review_ruleset=review_ruleset,
            design_ruleset=design_ruleset, index=index,
        ))

    if not mappings:
        mappings.append(RuleMapping(
            mapping_id=f"mapping:{rejection.rejection_id}:none",
            rejection_id=rejection.rejection_id, apple_guideline=None, mapped_rule_ids=(),
            category=RootCauseCategory.UNKNOWN, confidence=Confidence.LOW,
            evidence=(Evidence(kind="inspection", observed="no guideline number or known signal keyword found",
                                source="rejection_text"),),
            mapping_reason="No explicit guideline number or recognized signal keyword was found in the "
                           "rejection text.",
        ))
    return mappings
