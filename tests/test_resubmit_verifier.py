import unittest
from pathlib import Path

from ios_app_store_submit.resubmit.approval import create_approval
from ios_app_store_submit.resubmit.models import ExecutionStatus
from ios_app_store_submit.resubmit.planner import load_recovery_report, plan_resubmission
from ios_app_store_submit.resubmit.verifier import execute_resubmit, verify_execution, verify_post_submit_state


ROOT = Path(__file__).parents[1]
READY = ROOT / "fixtures" / "resubmit" / "resubmit_ready_verified" / "recovery-report.json"


class ResubmitVerifierTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_resubmission(load_recovery_report(READY))
        self.approval = create_approval(self.plan, approval_digest=self.plan.plan_digest)

    def test_execute_requires_approval_and_matching_digest(self):
        calls = []
        runner = lambda args: calls.append(args) or {"returncode": 0, "stdout": "WAITING_FOR_REVIEW"}
        result = execute_resubmit(self.plan, None, runner=runner)
        self.assertEqual(result.status, ExecutionStatus.NOT_RUN)
        self.assertEqual(calls, [])
        result = execute_resubmit(self.plan, self.approval, approval_digest="wrong", runner=runner)
        self.assertEqual(result.status, ExecutionStatus.NOT_RUN)
        self.assertEqual(calls, [])

    def test_execute_requires_current_matching_plan_and_reply_ready(self):
        changed = self.plan.__class__(**{**self.plan.to_dict(), "version": "2.0.1"})
        result = execute_resubmit(self.plan, self.approval, current_plan=changed, runner=lambda _: {"returncode": 0})
        self.assertEqual(result.status, ExecutionStatus.NOT_RUN)
        not_ready = self.plan.__class__(**{**self.plan.to_dict(), "ready": False})
        result = execute_resubmit(not_ready, self.approval, approval_digest=self.plan.plan_digest, runner=lambda _: {"returncode": 0})
        self.assertEqual(result.status, ExecutionStatus.NOT_RUN)

    def test_post_submit_success_requires_state_evidence(self):
        self.assertTrue(verify_post_submit_state("WAITING_FOR_REVIEW").verified)
        self.assertTrue(verify_post_submit_state({"reviewState": "IN_REVIEW"}).verified)
        for state in ("READY_FOR_REVIEW", "SUBMITTED", "PENDING_REVIEW"):
            result = verify_post_submit_state(state)
            self.assertFalse(result.verified, state)
            self.assertEqual(result.state, state)
        self.assertFalse(verify_post_submit_state("some command output").verified)
        self.assertEqual(verify_execution(0, "some command output").status, ExecutionStatus.FAILED)

    def test_failure_does_not_retry_or_mutate_additional_state(self):
        calls = []
        def runner(args):
            calls.append(args)
            return {"returncode": 9, "stdout": "failure"}
        result = execute_resubmit(self.plan, self.approval, approval_digest=self.plan.plan_digest, runner=runner)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result.retry_attempted)

    def test_verified_post_submit_state_is_required_for_success(self):
        mutation_calls = []
        def runner(args):
            mutation_calls.append(args)
            return {"returncode": 0, "stdout": "submitted"}
        result = execute_resubmit(
            self.plan, self.approval, approval_digest=self.plan.plan_digest, runner=runner,
            status_reader=lambda _: {"state": "WAITING_FOR_REVIEW"},
        )
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.post_submit.state, "WAITING_FOR_REVIEW")
        self.assertEqual(len(mutation_calls), 1)


if __name__ == "__main__":
    unittest.main()
