import json
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path

from ios_app_store_submit.recovery.models import RejectionMessage, RejectionSource
from ios_app_store_submit.recovery.parser import redacted_rejection_dict
from ios_app_store_submit.recovery.report import human_summary, run_recovery


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "recovery"
GENERATED_ASC_FILENAMES = {"readiness-report.json"}


def recovery(name):
    project = FIXTURES / name
    return run_recovery(project, project / "rejection.txt")


class RecoveryReportTests(unittest.TestCase):
    def test_json_round_trip_preserves_recovery_contract(self):
        result = recovery("reject_fixed_verified")
        encoded = result.to_dict()
        decoded = result.from_dict(json.loads(json.dumps(encoded)))
        self.assertEqual(decoded.to_dict(), encoded)
        self.assertIn("recovery_summary", encoded)
        self.assertIn("resubmit_candidate", encoded["recovery_summary"])

    def test_ordering_is_stable_independent_of_input_order(self):
        result = recovery("reject_partial_fix")
        shuffled = replace(
            result,
            mappings=tuple(reversed(result.mappings)),
            root_causes=tuple(reversed(result.root_causes)),
            fix_plans=tuple(reversed(result.fix_plans)),
            verification_results=tuple(reversed(result.verification_results)),
        )
        self.assertEqual(shuffled.to_dict(), result.to_dict())

    def test_raw_rejection_is_retained_locally_and_derived_output_is_redacted(self):
        result = recovery("reject_fixed_verified")
        self.assertIn("placeholder", result.rejection_dict["raw_text"])
        rejection = recovery("reject_demo_credentials_user_attested").rejection_dict
        self.assertNotIn("recovery-password", json.dumps(rejection))
        summary = human_summary(recovery("reject_demo_credentials_user_attested"))
        self.assertNotIn("2026-08-20", summary)

    def test_sensitive_values_are_redacted_from_serialized_rejection(self):
        rejection = RejectionMessage(
            rejection_id="secret", source=RejectionSource.MANUAL_TEXT, received_at="",
            raw_text="username: demo@example.com password: super-secret token: abc123",
        )
        serialized = json.dumps(redacted_rejection_dict(rejection))
        for secret in ("demo@example.com", "super-secret", "abc123"):
            self.assertNotIn(secret, serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_resubmit_yes_requires_all_required_conditions(self):
        verified = recovery("reject_fixed_verified")
        attested = recovery("reject_demo_credentials_user_attested")
        self.assertEqual(verified.resubmit_candidate, "YES")
        self.assertEqual(attested.resubmit_candidate, "YES")
        self.assertTrue(verified.reply_draft.ready_to_send)
        self.assertTrue(attested.reply_draft.ready_to_send)

    def test_unresolved_blocker_and_verification_produce_no(self):
        blocker = recovery("reject_guideline_2_1_missing_review_access")
        unverified = recovery("reject_fixed_unverified")
        self.assertEqual(blocker.resubmit_candidate, "NO")
        self.assertEqual(unverified.resubmit_candidate, "NO")
        self.assertFalse(blocker.reply_draft.ready_to_send)
        self.assertFalse(unverified.reply_draft.ready_to_send)

    def test_pending_confirmation_and_runtime_evidence_are_conditional(self):
        pending = recovery("reject_ambiguous_text")
        runtime = recovery("reject_guideline_2_1_crash_unknown")
        self.assertEqual(pending.resubmit_candidate, "CONDITIONAL")
        self.assertEqual(runtime.resubmit_candidate, "CONDITIONAL")

    def test_recovery_is_read_only_and_does_not_resubmit_or_mutate_external_services(self):
        recovery_root = ROOT / "ios_app_store_submit" / "recovery"
        source = "\n".join(path.read_text() for path in recovery_root.glob("*.py"))
        for forbidden in (
            "import subprocess", "subprocess.", "import requests", "import urllib", "import socket",
            "asc review submit", "asc metadata push", "curl ", "requests.",
            "write_text(", "unlink(", "os.remove(", "shutil.", "xcodebuild",
        ):
            self.assertNotIn(forbidden, source)

        self.assertIn("RESUBMIT_CANDIDATE=YES does not submit anything", human_summary(recovery("reject_fixed_verified")))

    def test_authored_recovery_asc_fixture_files_are_tracked(self):
        asc_files = sorted(FIXTURES.glob("*/.asc/*"))
        authored = [path for path in asc_files if path.name not in GENERATED_ASC_FILENAMES]
        self.assertTrue(authored, "expected an authored recovery fixture under fixtures/recovery/**/.asc/")
        for path in authored:
            relative = path.relative_to(ROOT).as_posix()
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", relative],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(
                result.returncode, 0,
                f"{relative} must be tracked as authored fixture input; force-add only this file if ignored.",
            )


if __name__ == "__main__":
    unittest.main()
