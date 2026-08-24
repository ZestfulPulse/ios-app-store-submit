import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.resubmit.approval import (
    approval_status, create_approval, load_approval, validate_approval, write_approval,
)
from ios_app_store_submit.resubmit.models import ApprovalDecision
from ios_app_store_submit.resubmit.planner import load_recovery_report, plan_resubmission


ROOT = Path(__file__).parents[1]
READY = ROOT / "fixtures" / "resubmit" / "resubmit_ready_verified" / "recovery-report.json"


class ResubmitApprovalTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_resubmission(load_recovery_report(READY))

    def test_no_approval_is_pending_and_not_executable(self):
        self.assertEqual(approval_status(self.plan, None), ApprovalDecision.PENDING)
        self.assertEqual(validate_approval(self.plan, None)[0], False)

    def test_approval_is_bound_to_exact_digest(self):
        record = create_approval(self.plan, approval_digest=self.plan.plan_digest)
        self.assertEqual(approval_status(self.plan, record), ApprovalDecision.APPROVED)
        self.assertTrue(validate_approval(self.plan, record, approval_digest=self.plan.plan_digest)[0])
        self.assertFalse(validate_approval(self.plan, record, approval_digest="wrong")[0])

    def test_plan_change_makes_approval_stale(self):
        record = create_approval(self.plan, approval_digest=self.plan.plan_digest)
        changed = self.plan.__class__(**{**self.plan.to_dict(), "version": "2.0.1"})
        self.assertEqual(approval_status(changed, record), ApprovalDecision.STALE)
        self.assertFalse(validate_approval(changed, record)[0])

    def test_approval_artifact_is_local_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_approval(directory, create_approval(self.plan, approval_digest=self.plan.plan_digest))
            self.assertEqual(path, (Path(directory) / ".asc" / "resubmit" / "approval.json").resolve())
            self.assertEqual(load_approval(directory).planned_submission_digest, self.plan.plan_digest)


if __name__ == "__main__":
    unittest.main()
