import unittest

from ios_app_store_submit.recovery.models import RecoveryFixPlan, RootCauseCandidate, RootCauseCategory, Safety
from ios_app_store_submit.recovery.planner import plan_recovery_fix
from ios_app_store_submit.readiness.models import Evidence
from ios_app_store_submit.review.models import Confidence


def root_cause(category, *, status="UNKNOWN"):
    return RootCauseCandidate(
        root_cause_id=f"rc:{category.value}", rejection_id="r1", category=category,
        title=f"{category.value} issue", hypothesis="a hypothesis", confidence=Confidence.MEDIUM,
        evidence=(Evidence(kind="text", observed=category.value),), missing_evidence=(),
        related_findings=(f"finding:{category.value}",), source_paths=("source.txt",),
        requires_runtime=False, requires_user_confirmation=True, status=status,
    )


class RecoveryPlannerBoundaryTests(unittest.TestCase):
    def test_recovery_categories_are_conservatively_partitioned(self):
        expected = {
            RootCauseCategory.METADATA: Safety.APPROVAL_REQUIRED,
            RootCauseCategory.TECHNICAL: Safety.MANUAL,
            RootCauseCategory.PERFORMANCE: Safety.MANUAL,
            RootCauseCategory.REVIEW_ACCESS: Safety.MANUAL,
            RootCauseCategory.DESIGN_HIG: Safety.MANUAL,
            RootCauseCategory.LOCALIZATION: Safety.MANUAL,
            RootCauseCategory.SCREENSHOT_ASSET: Safety.MANUAL,
            RootCauseCategory.UNKNOWN: Safety.MANUAL,
            RootCauseCategory.PRIVACY: Safety.FORBIDDEN,
            RootCauseCategory.PAYMENTS_IAP: Safety.FORBIDDEN,
            RootCauseCategory.LEGAL_POLICY: Safety.FORBIDDEN,
        }
        for category, safety in expected.items():
            with self.subTest(category=category.value):
                plan = plan_recovery_fix(root_cause(category))
                self.assertEqual(plan.safety, safety)
                self.assertTrue(plan.requires_user_approval)

    def test_safe_is_reserved_for_phase_two_and_not_granted_to_recovery(self):
        plans = [plan_recovery_fix(root_cause(category)) for category in RootCauseCategory]
        self.assertNotIn(Safety.SAFE, {plan.safety for plan in plans})
        safe_plan = RecoveryFixPlan(
            fix_id="safe:format", root_cause_id="rc:format", finding_ids=(), safety=Safety.SAFE,
            title="Normalize formatting", description="formatting only", target_paths=("x",),
            proposed_changes="existing Phase 2 safe rule", verification_plan="recheck",
            reply_claim_allowed=False, requires_user_approval=False,
        )
        self.assertFalse(safe_plan.requires_user_approval)

    def test_protected_categories_never_auto_fix(self):
        protected = {
            RootCauseCategory.PRIVACY: "App Privacy",
            RootCauseCategory.REVIEW_ACCESS: "credentials",
            RootCauseCategory.DESIGN_HIG: "UI semantics",
            RootCauseCategory.METADATA: "metadata",
        }
        for category in protected:
            with self.subTest(category=category.value):
                plan = plan_recovery_fix(root_cause(category))
                self.assertNotEqual(plan.safety, Safety.SAFE)
                self.assertTrue(plan.requires_user_approval)
                self.assertIn("no automatic change", plan.proposed_changes.lower())

    def test_bundle_signing_privacy_review_credentials_asc_and_ui_are_not_safe(self):
        categories = (
            RootCauseCategory.METADATA, RootCauseCategory.PRIVACY,
            RootCauseCategory.REVIEW_ACCESS, RootCauseCategory.DESIGN_HIG,
        )
        for category in categories:
            with self.subTest(category=category.value):
                plan = plan_recovery_fix(root_cause(category))
                self.assertIn(plan.safety, (Safety.APPROVAL_REQUIRED, Safety.MANUAL, Safety.FORBIDDEN))
                self.assertTrue(plan.requires_user_approval)


if __name__ == "__main__":
    unittest.main()
