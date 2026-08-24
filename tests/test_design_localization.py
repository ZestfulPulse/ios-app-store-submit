import unittest
from pathlib import Path

from ios_app_store_submit.design import localization
from ios_app_store_submit.design.models import load_ruleset
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name):
        inspector = ProjectInspector(FIXTURES / name)
        return {f.rule_id: f for f in localization.evaluate(inspector, self.ruleset)}

    def test_hardcoded_string_is_detected(self):
        finding = self._evaluate("design_hardcoded_text")["DESIGN.LOCALIZATION.HARDCODED_STRING"]
        self.assertEqual(finding.status.value, "RISK")
        self.assertTrue(finding.evidence)

    def test_localized_string_does_not_false_positive(self):
        finding = self._evaluate("design_localized_text")["DESIGN.LOCALIZATION.HARDCODED_STRING"]
        self.assertEqual(finding.status.value, "PASS")

    def test_missing_localization_key_is_detected(self):
        finding = self._evaluate("design_missing_localization_key")["DESIGN.LOCALIZATION.MISSING_KEY"]
        self.assertEqual(finding.status.value, "BLOCKED")
        symbols = {e.symbol for e in finding.evidence}
        self.assertIn("farewell", symbols)

    def test_fewer_than_two_resource_files_is_unknown_not_blocked(self):
        finding = self._evaluate("design_no_signals")["DESIGN.LOCALIZATION.MISSING_KEY"]
        self.assertEqual(finding.status.value, "UNKNOWN")
        self.assertNotEqual(finding.status.value, "BLOCKED")

    def test_no_translation_is_fabricated(self):
        finding = self._evaluate("design_missing_localization_key")["DESIGN.LOCALIZATION.MISSING_KEY"]
        for evidence in finding.evidence:
            self.assertNotEqual(evidence.kind, "fabricated_translation")
        self.assertIn("gap", finding.message.lower())

    def test_fixed_text_container_yields_localization_risk(self):
        finding = self._evaluate("design_fixed_text_container")["DESIGN.LOCALIZATION.FIXED_TEXT_CONTAINER"]
        self.assertEqual(finding.status.value, "RISK")
        self.assertNotEqual(finding.status.value, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
