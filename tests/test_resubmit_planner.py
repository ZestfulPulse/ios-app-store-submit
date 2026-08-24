import unittest
from pathlib import Path

from ios_app_store_submit.resubmit.models import ResubmitStatus
from ios_app_store_submit.resubmit.planner import load_recovery_report, plan_resubmission


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "resubmit"


class ResubmitPlannerTests(unittest.TestCase):
    def report(self, name):
        return load_recovery_report(FIXTURES / name / "recovery-report.json")

    def test_plan_is_read_only_and_digest_is_stable(self):
        report = self.report("resubmit_ready_verified")
        before = set((FIXTURES / "resubmit_ready_verified").iterdir())
        plan = plan_resubmission(report)
        after = set((FIXTURES / "resubmit_ready_verified").iterdir())
        self.assertEqual(before, after)
        self.assertTrue(plan.ready)
        self.assertTrue(plan.digest_valid)

    def test_plan_uses_exact_discovered_ids(self):
        plan = plan_resubmission(self.report("resubmit_ready_verified"))
        self.assertEqual(plan.app_id, "123456789")
        self.assertEqual(plan.version, "2.0.0")
        self.assertEqual(plan.build_id, "200")
        self.assertEqual(plan.submission_id, "submission-ready")

    def test_missing_ids_block_plan_and_commands(self):
        missing_build = plan_resubmission(self.report("resubmit_missing_build_id"))
        missing_submission = plan_resubmission(self.report("resubmit_missing_submission_id"))
        self.assertFalse(missing_build.ready)
        self.assertIn("missing_build_id", missing_build.blockers)
        self.assertIn("missing_submission_id", missing_submission.blockers)
        self.assertEqual(missing_build.commands, ())

    def test_conditional_recovery_is_not_ready(self):
        plan = plan_resubmission(self.report("resubmit_conditional_user_confirmation"))
        self.assertEqual(plan.eligibility, ResubmitStatus.CONDITIONAL)
        self.assertFalse(plan.ready)


if __name__ == "__main__":
    unittest.main()
