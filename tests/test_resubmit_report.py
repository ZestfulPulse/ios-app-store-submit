import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.resubmit.approval import create_approval
from ios_app_store_submit.resubmit.eligibility import evaluate_eligibility
from ios_app_store_submit.resubmit.models import ExecutionResult, ExecutionStatus
from ios_app_store_submit.resubmit.planner import load_recovery_report, plan_resubmission
from ios_app_store_submit.resubmit.report import build_report, human_summary


ROOT = Path(__file__).parents[1]
READY = ROOT / "fixtures" / "resubmit" / "resubmit_ready_verified" / "recovery-report.json"


class ResubmitReportTests(unittest.TestCase):
    def test_report_has_required_human_contract(self):
        recovery = load_recovery_report(READY)
        plan = plan_resubmission(recovery)
        report = build_report(evaluate_eligibility(recovery), plan)
        text = human_summary(report)
        for label in ("=== CLOSED-LOOP RESUBMISSION ===", "RECOVERY_GATE:", "PLAN:", "APPROVAL:", "EXECUTION:", "POST_SUBMIT_STATE:", "FINAL:"):
            self.assertIn(label, text)
        self.assertIn("PENDING", text)
        self.assertIn("Nothing should be submitted", text)

    def test_approved_verified_report_round_trip(self):
        recovery = load_recovery_report(READY)
        plan = plan_resubmission(recovery)
        approval = create_approval(plan, approval_digest=plan.plan_digest)
        report = build_report(evaluate_eligibility(recovery), plan, approval, ExecutionResult("SUCCESS", post_submit={"state": "WAITING_FOR_REVIEW", "verified": True}))
        encoded = report.to_dict()
        self.assertEqual(report.final, "RESUBMITTED_VERIFIED")
        self.assertEqual(json.loads(json.dumps(encoded))["plan"]["plan_digest"], plan.plan_digest)

    def test_default_cli_plan_is_read_only_and_does_not_create_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", directory, "--resubmit-plan", str(READY)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)  # a dry-run plan is allowed; it is not executable
            self.assertFalse((Path(directory) / ".asc" / "resubmit" / "approval.json").exists())
            self.assertIn("CLOSED-LOOP RESUBMISSION", result.stdout)

    def test_existing_submission_flow_remains_documented(self):
        skill = (ROOT / "SKILL.md").read_text()
        for required in ("asc xcode archive", "asc publish appstore", "asc review submit", "WAITING_FOR_REVIEW"):
            self.assertIn(required, skill)


if __name__ == "__main__":
    unittest.main()
