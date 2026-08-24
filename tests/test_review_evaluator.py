import json
import subprocess
import sys
import unittest
from pathlib import Path

from ios_app_store_submit.review.evaluator import PreReviewResult, human_summary, run_pre_review
from ios_app_store_submit.review.models import ReviewFinding

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class GateAggregationTests(unittest.TestCase):
    def test_any_blocked_gives_blocked_gate(self):
        result = run_pre_review(FIXTURES / "review_placeholder_metadata")
        self.assertEqual(result.gate, "BLOCKED")
        self.assertGreater(result.counts["BLOCKED"], 0)

    def test_unknown_without_blocked_gives_conditional_gate(self):
        result = run_pre_review(FIXTURES / "review_valid_basic")
        self.assertEqual(result.gate, "CONDITIONAL")
        self.assertEqual(result.counts["BLOCKED"], 0)
        self.assertGreater(result.counts["UNKNOWN"], 0)

    def test_risk_alone_does_not_force_conditional_or_blocked(self):
        result = run_pre_review(FIXTURES / "review_login_with_demo_evidence")
        statuses = {f.status.value for f in result.findings}
        self.assertIn("RISK", statuses)
        self.assertNotIn("BLOCKED", statuses)
        if "UNKNOWN" not in statuses:
            self.assertEqual(result.gate, "PASS")


class StableOrderingTests(unittest.TestCase):
    def test_ordered_findings_are_stable_across_runs(self):
        first = run_pre_review(FIXTURES / "review_valid_basic").ordered_findings()
        second = run_pre_review(FIXTURES / "review_valid_basic").ordered_findings()
        self.assertEqual([f.rule_id for f in first], [f.rule_id for f in second])
        categories = [f.category for f in first]
        # PERFORMANCE findings must all precede METADATA, which must precede
        # REVIEW_ACCESS, which must precede PRIVACY.
        seen = []
        for category in categories:
            if not seen or seen[-1] != category:
                seen.append(category)
        self.assertEqual(seen, sorted(seen, key=["PERFORMANCE", "METADATA", "REVIEW_ACCESS", "PRIVACY"].index))


class JsonRoundTripTests(unittest.TestCase):
    def test_pre_review_result_round_trips(self):
        result = run_pre_review(FIXTURES / "review_login_without_demo_evidence")
        restored = PreReviewResult.from_dict(json.loads(json.dumps(result.to_dict())))
        self.assertEqual(restored.gate, result.gate)
        self.assertEqual(
            [f.finding_id for f in restored.ordered_findings()],
            [f.finding_id for f in result.ordered_findings()],
        )


class CliIntegrationTests(unittest.TestCase):
    def test_pre_review_json_extends_readiness_report(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "review_valid_basic"),
             "--pre-review", "--json"],
            cwd=ROOT, capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        for key in ("pre_review", "ruleset", "review_findings", "review_summary", "ready", "findings"):
            self.assertIn(key, payload)
        self.assertEqual(payload["pre_review"], "CONDITIONAL")

    def test_strict_unknown_causes_nonzero_exit(self):
        lenient = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "review_valid_basic"), "--pre-review"],
            cwd=ROOT, capture_output=True, text=True,
        )
        strict = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "review_valid_basic"),
             "--pre-review", "--strict"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(strict.returncode, 1)
        # Non-strict CONDITIONAL is not itself a failure at the pre-review layer.
        self.assertIn("CONDITIONAL", lenient.stdout)

    def test_blocked_pre_review_causes_nonzero_exit_even_without_strict(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "review_placeholder_metadata"),
             "--pre-review"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)

    def test_pre_review_output_precedes_existing_readiness_summary(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "review_valid_basic"), "--pre-review"],
            cwd=ROOT, capture_output=True, text=True,
        )
        pre_review_at = result.stdout.index("=== APP STORE PRE-REVIEW ===")
        readiness_at = result.stdout.index("=== IOS APP STORE READINESS SUMMARY ===")
        self.assertLess(pre_review_at, readiness_at)

    def test_pre_review_causes_zero_mutation(self):
        import hashlib
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "project"
            shutil.copytree(FIXTURES / "review_valid_basic", target, ignore=shutil.ignore_patterns(".asc"))
            before = {p.relative_to(target): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in target.rglob("*") if p.is_file()}
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(target), "--pre-review", "--plan-fixes"],
                cwd=ROOT, capture_output=True, text=True,
            )
            after = {p.relative_to(target): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in target.rglob("*") if p.is_file()}
            self.assertEqual(result.returncode, 0)
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
