"""Plan (never auto-apply) a recovery fix for each root cause.

Phase 6 may PLAN a fix for any category, but only the existing Phase 2 SAFE
formatting/scaffolding rules may ever auto-apply anything; every category
that touches bundle ID, signing, entitlements, privacy declarations, review
credentials, pricing, legal/policy content, IAP configuration, ASC
metadata, UI semantics/layout, or submission itself is planned as
APPROVAL_REQUIRED/MANUAL/FORBIDDEN only, never SAFE.
"""

from __future__ import annotations

from .models import RecoveryFixPlan, RootCauseCandidate, RootCauseCategory, Safety

# Conservative, fixed per-category safety ceiling. Nothing in Phase 6 ever
# raises a category's safety above what is listed here.
_CATEGORY_SAFETY = {
    RootCauseCategory.TECHNICAL: Safety.MANUAL,
    RootCauseCategory.PERFORMANCE: Safety.MANUAL,
    RootCauseCategory.METADATA: Safety.APPROVAL_REQUIRED,
    RootCauseCategory.PRIVACY: Safety.FORBIDDEN,
    RootCauseCategory.REVIEW_ACCESS: Safety.MANUAL,
    RootCauseCategory.DESIGN_HIG: Safety.MANUAL,
    RootCauseCategory.LOCALIZATION: Safety.MANUAL,
    RootCauseCategory.SCREENSHOT_ASSET: Safety.MANUAL,
    RootCauseCategory.PAYMENTS_IAP: Safety.FORBIDDEN,
    RootCauseCategory.LEGAL_POLICY: Safety.FORBIDDEN,
    RootCauseCategory.UNKNOWN: Safety.MANUAL,
}

_CATEGORY_DESCRIPTION = {
    RootCauseCategory.TECHNICAL: "Investigate and fix the reported crash/stability issue; requires a real "
                                  "code change and device/simulator verification, never auto-applied.",
    RootCauseCategory.PERFORMANCE: "Review and correct the reported completeness/performance issue.",
    RootCauseCategory.METADATA: "Update the flagged metadata field. A pure formatting/scaffolding fix may "
                                 "reuse Phase 2's existing SAFE rules; content changes require approval.",
    RootCauseCategory.PRIVACY: "Review and correct the App Privacy declaration in App Store Connect. This is "
                                "never auto-changed by this tool.",
    RootCauseCategory.REVIEW_ACCESS: "Provide or correct working demo/review account credentials in App "
                                      "Store Connect review notes. Credentials are never invented or "
                                      "auto-filled by this tool.",
    RootCauseCategory.DESIGN_HIG: "Adjust the flagged UI element (size/label/layout). UI semantics are never "
                                   "auto-changed by this tool.",
    RootCauseCategory.LOCALIZATION: "Correct or add the missing/incorrect localized content. Translations "
                                     "are never fabricated by this tool.",
    RootCauseCategory.SCREENSHOT_ASSET: "Replace or update the flagged screenshot/asset. Never captured or "
                                         "generated automatically by this tool.",
    RootCauseCategory.PAYMENTS_IAP: "Correct the flagged In-App Purchase/pricing configuration in App Store "
                                     "Connect. Never auto-changed by this tool.",
    RootCauseCategory.LEGAL_POLICY: "Address the flagged legal/policy concern. Requires human legal "
                                     "judgment; never auto-changed by this tool.",
    RootCauseCategory.UNKNOWN: "Classify the concern more precisely (more specific rejection text or an "
                                "explicit guideline number) before a fix can be planned.",
}


def plan_recovery_fix(root_cause: RootCauseCandidate) -> RecoveryFixPlan:
    safety = _CATEGORY_SAFETY[root_cause.category]
    reply_claim_allowed = root_cause.status.value == "CONFIRMED"
    return RecoveryFixPlan(
        fix_id=f"fix:{root_cause.root_cause_id}",
        root_cause_id=root_cause.root_cause_id,
        finding_ids=root_cause.related_findings,
        safety=safety,
        title=f"Address {root_cause.title.lower()}",
        description=_CATEGORY_DESCRIPTION[root_cause.category],
        target_paths=root_cause.source_paths,
        proposed_changes="No automatic change is proposed by Phase 6; this plan describes what a human "
                          "should do and how it will be verified afterward.",
        verification_plan=f"Re-run the {root_cause.category.value.lower()} readiness/pre-review/privacy/"
                           "design check(s) referenced by related_findings and confirm they no longer show "
                           "BLOCKED/RISK for this cause.",
        reply_claim_allowed=reply_claim_allowed,
        requires_user_approval=safety is not Safety.SAFE,
        status="PLANNED",
    )


def plan_recovery_fixes(root_causes: list[RootCauseCandidate]) -> list[RecoveryFixPlan]:
    return [plan_recovery_fix(root_cause) for root_cause in root_causes]
