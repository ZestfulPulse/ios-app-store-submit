import unittest
from types import SimpleNamespace

from ios_app_store_submit.recovery.models import (
    ClaimStatus, RootCauseCandidate, RootCauseCategory, RootCauseStatus,
)
from ios_app_store_submit.recovery.planner import plan_recovery_fix
from ios_app_store_submit.recovery.verifier import verify_root_cause
from ios_app_store_submit.readiness.models import Evidence
from ios_app_store_submit.review.models import Confidence


def root_cause(category=RootCauseCategory.METADATA, *, status=RootCauseStatus.CONFIRMED,
               requires_runtime=False, requires_user_confirmation=False):
    return RootCauseCandidate(
        root_cause_id="rc:test", rejection_id="r1", category=category, title="Issue",
        hypothesis="hypothesis", confidence=Confidence.HIGH,
        evidence=(Evidence(kind="deterministic", observed="evidence"),), missing_evidence=(),
        related_findings=("finding:one",), source_paths=(), requires_runtime=requires_runtime,
        requires_user_confirmation=requires_user_confirmation, status=status,
    )


def review_result(status):
    return SimpleNamespace(category_status={"METADATA": status})


class RecoveryVerifierTests(unittest.TestCase):
    def test_verified_fix_requires_current_pass(self):
        result = verify_root_cause(root_cause(), pre_review_result=review_result("PASS"))
        self.assertEqual(result.claim_status, ClaimStatus.VERIFIED)
        self.assertEqual(result.pending_reason, None)
        self.assertIn("finding:one", result.rechecked_rule_ids)
        self.assertTrue(result.evidence)

    def test_unverified_fix_stays_unverified_when_recheck_is_unavailable(self):
        result = verify_root_cause(root_cause())
        self.assertEqual(result.claim_status, ClaimStatus.UNVERIFIED)
        self.assertEqual(result.pending_reason, "still_blocked")

    def test_user_attestation_is_explicitly_distinct_from_local_verification(self):
        result = verify_root_cause(
            root_cause(), attestations={"METADATA": {"attested": True, "note": "User checked it."}},
        )
        self.assertEqual(result.claim_status, ClaimStatus.USER_ATTESTED)
        self.assertEqual(result.evidence[0].source, "user")

    def test_failed_verify_never_becomes_success(self):
        result = verify_root_cause(root_cause(), pre_review_result=review_result("BLOCKED"))
        self.assertEqual(result.claim_status, ClaimStatus.UNVERIFIED)
        self.assertEqual(result.pending_reason, "still_blocked")
        self.assertNotEqual(result.claim_status, ClaimStatus.VERIFIED)

    def test_stale_pass_evidence_cannot_override_current_contradictory_blocker(self):
        candidate = root_cause(status=RootCauseStatus.CONTRADICTED)
        result = verify_root_cause(candidate, pre_review_result=review_result("BLOCKED"))
        self.assertEqual(result.claim_status, ClaimStatus.UNVERIFIED)
        self.assertNotEqual(result.claim_status, ClaimStatus.VERIFIED)

    def test_runtime_required_fix_cannot_be_claimed_without_runtime_evidence(self):
        result = verify_root_cause(root_cause(requires_runtime=True))
        self.assertEqual(result.claim_status, ClaimStatus.UNVERIFIED)
        self.assertEqual(result.pending_reason, "requires_runtime")

    def test_reply_claim_allowed_only_when_claim_gate_allows_it(self):
        confirmed_plan = plan_recovery_fix(root_cause(status=RootCauseStatus.CONFIRMED))
        unresolved_plan = plan_recovery_fix(root_cause(status=RootCauseStatus.UNKNOWN))
        self.assertTrue(confirmed_plan.reply_claim_allowed)
        self.assertFalse(unresolved_plan.reply_claim_allowed)


if __name__ == "__main__":
    unittest.main()
