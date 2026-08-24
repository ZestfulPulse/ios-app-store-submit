import unittest
from pathlib import Path

from ios_app_store_submit.design import layout
from ios_app_store_submit.design.models import load_ruleset
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name):
        inspector = ProjectInspector(FIXTURES / name)
        return {f.rule_id: f for f in layout.evaluate(inspector, self.ruleset)}

    def test_safe_area_present_is_pass(self):
        finding = self._evaluate("design_safe_area_present")["DESIGN.LAYOUT.SAFE_AREA"]
        self.assertEqual(finding.status.value, "PASS")

    def test_safe_area_absent_is_unknown_not_blocked(self):
        finding = self._evaluate("design_safe_area_unknown")["DESIGN.LAYOUT.SAFE_AREA"]
        self.assertEqual(finding.status.value, "UNKNOWN")
        self.assertNotEqual(finding.status.value, "BLOCKED")
        self.assertTrue(finding.evidence[0].runtime_required)

    def test_no_scaffold_is_pass(self):
        finding = self._evaluate("design_no_signals")["DESIGN.LAYOUT.SAFE_AREA"]
        self.assertEqual(finding.status.value, "PASS")

    def test_hardcoded_screen_dimensions_are_risk_never_blocked(self):
        finding = self._evaluate("design_valid_basic")["DESIGN.LAYOUT.HARDCODED_DIMENSIONS"]
        self.assertIn(finding.status.value, ("PASS", "RISK"))
        self.assertNotEqual(finding.status.value, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
