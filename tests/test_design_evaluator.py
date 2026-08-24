import json
import unittest
from pathlib import Path

from ios_app_store_submit.design.evaluator import DesignReviewResult, run_design_review

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class GateAggregationTests(unittest.TestCase):
    def test_any_blocked_gives_blocked_gate(self):
        result = run_design_review(FIXTURES / "design_small_explicit_control")
        self.assertEqual(result.gate, "BLOCKED")
        self.assertGreater(result.counts["BLOCKED"], 0)

    def test_unknown_without_blocked_gives_conditional_gate(self):
        result = run_design_review(FIXTURES / "design_control_size_unknown")
        self.assertEqual(result.gate, "CONDITIONAL")
        self.assertEqual(result.counts["BLOCKED"], 0)
        self.assertGreater(result.counts["UNKNOWN"], 0)

    def test_risk_alone_does_not_force_conditional_or_blocked(self):
        result = run_design_review(FIXTURES / "design_permission_context_risk")
        statuses = {f.status.value for f in result.findings}
        self.assertIn("RISK", statuses)
        self.assertNotIn("BLOCKED", statuses)
        if "UNKNOWN" not in statuses:
            self.assertEqual(result.gate, "PASS")


class StableOrderingTests(unittest.TestCase):
    def test_ordered_findings_are_stable_across_runs(self):
        first = run_design_review(FIXTURES / "design_valid_basic").ordered_findings()
        second = run_design_review(FIXTURES / "design_valid_basic").ordered_findings()
        self.assertEqual([f.rule_id for f in first], [f.rule_id for f in second])
        areas = [f.hig_area for f in first]
        seen = []
        for area in areas:
            if not seen or seen[-1] != area:
                seen.append(area)
        self.assertEqual(seen, sorted(seen, key=["ACCESSIBILITY", "LAYOUT", "LOCALIZATION", "INTERACTION"].index))


class JsonRoundTripTests(unittest.TestCase):
    def test_result_round_trips(self):
        result = run_design_review(FIXTURES / "design_missing_localization_key")
        restored = DesignReviewResult.from_dict(json.loads(json.dumps(result.to_dict())))
        self.assertEqual(restored.gate, result.gate)
        self.assertEqual(
            [f.finding_id for f in restored.ordered_findings()],
            [f.finding_id for f in result.ordered_findings()],
        )


class NoUiMutationTests(unittest.TestCase):
    def test_design_modules_never_open_files_for_writing(self):
        package_root = ROOT / "ios_app_store_submit" / "design"
        for path in package_root.glob("*.py"):
            text = path.read_text()
            self.assertNotIn('"w")', text, path)
            self.assertNotIn("'w')", text, path)
            self.assertNotIn(".write_text(", text, path)
            self.assertNotIn(".write_bytes(", text, path)

    def test_no_simulator_or_device_or_network_or_shell_out(self):
        package_root = ROOT / "ios_app_store_submit" / "design"
        forbidden = (
            "subprocess", "os.system", "os.popen", "urllib", "requests", "httpx", "socket.",
            "xcrun", "simctl", "instruments",
        )
        for path in package_root.glob("*.py"):
            text = path.read_text()
            for token in forbidden:
                self.assertNotIn(token, text, f"{path} references {token!r}")


if __name__ == "__main__":
    unittest.main()
