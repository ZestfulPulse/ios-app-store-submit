import unittest
from pathlib import Path

from ios_app_store_submit.design import accessibility
from ios_app_store_submit.design.models import load_ruleset
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class AccessibilityTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name):
        inspector = ProjectInspector(FIXTURES / name)
        return {f.rule_id: f for f in accessibility.evaluate(inspector, self.ruleset)}

    def test_explicit_undersized_control_is_deterministic_blocked(self):
        finding = self._evaluate("design_small_explicit_control")["DESIGN.ACCESSIBILITY.TOUCH_TARGET_SIZE"]
        self.assertEqual(finding.status.value, "BLOCKED")
        self.assertEqual(finding.check_type.value, "DETERMINISTIC")
        self.assertTrue(finding.evidence)

    def test_unknown_rendered_size_stays_unknown_not_pass(self):
        finding = self._evaluate("design_control_size_unknown")["DESIGN.ACCESSIBILITY.TOUCH_TARGET_SIZE"]
        self.assertEqual(finding.status.value, "UNKNOWN")
        self.assertNotEqual(finding.status.value, "PASS")
        self.assertTrue(finding.evidence[0].runtime_required)

    def test_no_interactive_controls_is_pass(self):
        finding = self._evaluate("design_no_signals")["DESIGN.ACCESSIBILITY.TOUCH_TARGET_SIZE"]
        self.assertEqual(finding.status.value, "PASS")

    def test_unlabeled_icon_only_control_is_blocked(self):
        finding = self._evaluate("design_icon_button_no_semantics")["DESIGN.ACCESSIBILITY.ICON_BUTTON_SEMANTIC_LABEL"]
        self.assertEqual(finding.status.value, "BLOCKED")

    def test_labeled_icon_button_is_pass(self):
        finding = self._evaluate("design_valid_basic")["DESIGN.ACCESSIBILITY.ICON_BUTTON_SEMANTIC_LABEL"]
        self.assertEqual(finding.status.value, "PASS")

    def test_hardcoded_font_size_is_risk_never_blocked(self):
        inspector = ProjectInspector(FIXTURES / "design_valid_basic")
        finding = accessibility._dynamic_type(inspector, self.ruleset)
        self.assertIn(finding.status.value, ("PASS", "RISK"))
        self.assertNotEqual(finding.status.value, "BLOCKED")

    def test_supplied_rendered_size_evidence_resolves_unknown_control(self):
        inspector = ProjectInspector(FIXTURES / "design_runtime_evidence_required")
        without_evidence = accessibility._touch_target_size(inspector, self.ruleset, None)
        self.assertEqual(without_evidence.status.value, "UNKNOWN")

        design_evidence = {"rendered_sizes": {"primaryActionButton": {"width": 48, "height": 48}}}
        with_evidence = accessibility._touch_target_size(inspector, self.ruleset, design_evidence)
        self.assertEqual(with_evidence.status.value, "PASS")

        undersized_evidence = {"rendered_sizes": {"primaryActionButton": {"width": 20, "height": 20}}}
        blocked = accessibility._touch_target_size(inspector, self.ruleset, undersized_evidence)
        self.assertEqual(blocked.status.value, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
