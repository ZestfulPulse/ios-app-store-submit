import unittest
from pathlib import Path

from ios_app_store_submit.design import interaction
from ios_app_store_submit.design.models import load_ruleset
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name):
        inspector = ProjectInspector(FIXTURES / name)
        return {f.rule_id: f for f in interaction.evaluate(inspector, self.ruleset)}

    def test_gesture_only_interaction_is_detected(self):
        finding = self._evaluate("design_gesture_only")["DESIGN.INTERACTION.GESTURE_ONLY"]
        self.assertEqual(finding.status.value, "RISK")
        self.assertNotEqual(finding.status.value, "BLOCKED")

    def test_labeled_control_is_pass(self):
        finding = self._evaluate("design_valid_basic")["DESIGN.INTERACTION.GESTURE_ONLY"]
        self.assertEqual(finding.status.value, "PASS")

    def test_permission_context_risk_is_detected(self):
        finding = self._evaluate("design_permission_context_risk")["DESIGN.INTERACTION.PERMISSION_CONTEXT"]
        self.assertEqual(finding.status.value, "RISK")
        self.assertNotEqual(finding.status.value, "BLOCKED")

    def test_no_permission_calls_is_pass(self):
        finding = self._evaluate("design_no_signals")["DESIGN.INTERACTION.PERMISSION_CONTEXT"]
        self.assertEqual(finding.status.value, "PASS")

    def test_no_subjective_aesthetic_blocker(self):
        for name in ("design_valid_basic", "design_gesture_only", "design_permission_context_risk"):
            for finding in self._evaluate(name).values():
                self.assertNotIn("confusing", finding.message.lower())
                self.assertNotIn("ugly", finding.message.lower())
                self.assertNotIn("feels", finding.message.lower())


if __name__ == "__main__":
    unittest.main()
