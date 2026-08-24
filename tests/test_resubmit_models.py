import json
import unittest
from dataclasses import replace

from ios_app_store_submit.resubmit.models import (
    ApprovalDecision, ApprovalRecord, ResubmitPlan, ResubmitStatus, stable_digest,
)


class ResubmitModelsTests(unittest.TestCase):
    def test_enums_and_json_round_trip_are_stable(self):
        plan = ResubmitPlan(
            plan_id="resubmit:test", app_id="app", version="2.0.0", build_id="42", submission_id="sub",
            reply_draft_id="reply", recovery_report_id="recovery", required_actions=("reply",),
            blockers=(), commands=("asc review submit --app app",), selected_command="asc review submit --app app",
            evidence_digest="evidence", eligibility=ResubmitStatus.YES, ready=True,
        )
        plan = replace(plan, plan_digest=plan.computed_digest)
        decoded = ResubmitPlan.from_dict(json.loads(json.dumps(plan.to_dict(), sort_keys=True)))
        self.assertEqual(decoded.to_dict(), plan.to_dict())
        self.assertEqual(stable_digest({"b": 2, "a": 1}), stable_digest({"a": 1, "b": 2}))

    def test_approval_record_round_trip(self):
        record = ApprovalRecord("approval:1", "resubmit:test", ApprovalDecision.PENDING, notes="review")
        self.assertEqual(ApprovalRecord.from_dict(record.to_dict()).to_dict(), record.to_dict())


if __name__ == "__main__":
    unittest.main()
