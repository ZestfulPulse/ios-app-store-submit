import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ios_app_store_submit.privacy.report import PrivacyIntelligenceResult, run_privacy_intelligence

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class GateTests(unittest.TestCase):
    def test_structural_manifest_defect_blocks(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_manifest_invalid")
        self.assertEqual(result.gate, "BLOCKED")

    def test_missing_required_reason_manifest_entry_blocks(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_required_reason_missing")
        self.assertEqual(result.gate, "BLOCKED")

    def test_no_signals_is_not_automatically_pass(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_no_signals")
        self.assertNotEqual(result.gate, "PASS")

    def test_contradiction_is_conditional_not_blocked_by_default(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_sdk_analytics_present")
        self.assertEqual(result.gate, "CONDITIONAL")


class PrivacyPolicyTests(unittest.TestCase):
    def test_missing_privacy_policy_url_is_unknown_not_fabricated(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_policy_missing")
        self.assertEqual(result.privacy_policy_status, "UNKNOWN")
        self.assertNotEqual(result.gate, "PASS")


class JsonRoundTripTests(unittest.TestCase):
    def test_result_round_trips(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_contradicted")
        restored = PrivacyIntelligenceResult.from_dict(json.loads(json.dumps(result.to_dict())))
        self.assertEqual(restored.gate, result.gate)
        self.assertEqual(
            [e.evidence_id for e in restored.ordered_evidence()],
            [e.evidence_id for e in result.ordered_evidence()],
        )
        self.assertEqual(
            [c.candidate_id for c in restored.ordered_candidates()],
            [c.candidate_id for c in result.ordered_candidates()],
        )


class StableOrderingTests(unittest.TestCase):
    def test_ordering_is_stable_across_runs(self):
        first = run_privacy_intelligence(FIXTURES / "privacy_contradicted")
        second = run_privacy_intelligence(FIXTURES / "privacy_contradicted")
        self.assertEqual(
            [e.evidence_id for e in first.ordered_evidence()],
            [e.evidence_id for e in second.ordered_evidence()],
        )
        self.assertEqual(
            [c.candidate_id for c in first.ordered_candidates()],
            [c.candidate_id for c in second.ordered_candidates()],
        )


class NoMutationTests(unittest.TestCase):
    def test_no_network_access_by_default(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network access attempted")):
            result = run_privacy_intelligence(FIXTURES / "privacy_contradicted")
        self.assertTrue(result.evidence)

    def test_privacy_modules_never_open_files_for_writing(self):
        package_root = ROOT / "ios_app_store_submit" / "privacy"
        for path in package_root.glob("*.py"):
            text = path.read_text()
            self.assertNotIn('"w")', text, path)
            self.assertNotIn("'w')", text, path)
            self.assertNotIn(".write_text(", text, path)
            self.assertNotIn(".write_bytes(", text, path)

    def test_privacy_modules_never_shell_out_or_touch_the_network(self):
        package_root = ROOT / "ios_app_store_submit" / "privacy"
        forbidden = ("subprocess", "os.system", "os.popen", "urllib", "requests", "httpx", "socket.")
        for path in package_root.glob("*.py"):
            text = path.read_text()
            for token in forbidden:
                self.assertNotIn(token, text, f"{path} references {token!r}")

    def test_privacy_run_causes_zero_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "project"
            shutil.copytree(FIXTURES / "privacy_contradicted", target)
            before = {p.relative_to(target): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in target.rglob("*") if p.is_file()}
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(target), "--privacy", "--plan-fixes"],
                cwd=ROOT, capture_output=True, text=True,
            )
            after = {p.relative_to(target): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in target.rglob("*") if p.is_file()}
            self.assertEqual(result.returncode, 0)
            self.assertEqual(before, after)


class CliIntegrationTests(unittest.TestCase):
    def test_privacy_json_extends_readiness_report(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "privacy_permission_only"),
             "--privacy", "--json"],
            cwd=ROOT, capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        for key in ("privacy_intelligence", "privacy_evidence", "privacy_candidates",
                    "privacy_contradictions", "privacy_unknowns", "privacy_summary", "ready", "findings"):
            self.assertIn(key, payload)

    def test_privacy_output_precedes_existing_readiness_summary(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "privacy_permission_only"), "--privacy"],
            cwd=ROOT, capture_output=True, text=True,
        )
        privacy_at = result.stdout.index("=== APP PRIVACY INTELLIGENCE ===")
        readiness_at = result.stdout.index("=== IOS APP STORE READINESS SUMMARY ===")
        self.assertLess(privacy_at, readiness_at)

    def test_blocked_privacy_gate_causes_nonzero_exit(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "privacy_manifest_invalid"), "--privacy"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)

    def test_strict_conditional_privacy_gate_causes_nonzero_exit(self):
        lenient = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "privacy_permission_only"), "--privacy"],
            cwd=ROOT, capture_output=True, text=True,
        )
        strict = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "privacy_permission_only"),
             "--privacy", "--strict"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(lenient.returncode, 0)
        self.assertEqual(strict.returncode, 1)

    def test_pre_review_and_privacy_can_run_together(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "privacy_permission_only"),
             "--privacy", "--pre-review"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertIn("=== APP PRIVACY INTELLIGENCE ===", result.stdout)
        self.assertIn("=== APP STORE PRE-REVIEW ===", result.stdout)
        self.assertIn("=== IOS APP STORE READINESS SUMMARY ===", result.stdout)


class SubmissionFlowRegressionTests(unittest.TestCase):
    def test_existing_submission_flow_and_scripts_are_untouched(self):
        skill = (ROOT / "SKILL.md").read_text()
        for text in ("asc xcode archive", "asc publish appstore", "asc review submit", "WAITING_FOR_REVIEW"):
            self.assertIn(text, skill)
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", "scripts/gen_app_icons.py", "scripts/setup_build_keychain.sh"],
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
