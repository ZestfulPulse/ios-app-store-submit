import unittest
from pathlib import Path

from ios_app_store_submit.resubmit.eligibility import evaluate_eligibility
from ios_app_store_submit.resubmit.models import ResubmitStatus
from ios_app_store_submit.resubmit.planner import load_recovery_report


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "resubmit"


class ResubmitEligibilityTests(unittest.TestCase):
    def report(self, name):
        return load_recovery_report(FIXTURES / name / "recovery-report.json")

    def test_verified_recovery_is_eligible(self):
        result = evaluate_eligibility(self.report("resubmit_ready_verified"))
        self.assertEqual(result.status, ResubmitStatus.YES)

    def test_unresolved_blocker_is_no(self):
        result = evaluate_eligibility(self.report("resubmit_blocked_unverified"))
        self.assertEqual(result.status, ResubmitStatus.NO)
        self.assertIn("unverified_machine_issue", result.blockers)

    def test_only_user_confirmation_is_conditional(self):
        result = evaluate_eligibility(self.report("resubmit_conditional_user_confirmation"))
        self.assertEqual(result.status, ResubmitStatus.CONDITIONAL)

    def test_forbidden_claim_and_stale_state_block(self):
        report = self.report("resubmit_ready_verified")
        report["verification_results"][0]["claim_status"] = "FORBIDDEN_TO_CLAIM"
        report["stale_build_version"] = True
        result = evaluate_eligibility(report)
        self.assertEqual(result.status, ResubmitStatus.NO)
        self.assertIn("forbidden_claim", result.blockers)
        self.assertIn("stale_build_version", result.blockers)

    def test_unresolved_blocked_finding_in_combined_report_blocks(self):
        report = self.report("resubmit_ready_verified")
        report["review_findings"] = [{"finding_id": "review:blocker", "status": "BLOCKED"}]
        result = evaluate_eligibility(report)
        self.assertEqual(result.status, ResubmitStatus.NO)
        self.assertIn("unresolved_blocked_findings", result.blockers)


if __name__ == "__main__":
    unittest.main()
