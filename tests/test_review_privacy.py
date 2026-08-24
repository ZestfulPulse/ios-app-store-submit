import unittest
from pathlib import Path

from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.report import build_report
from ios_app_store_submit.review.registry import load_ruleset
from ios_app_store_submit.review.rules import privacy

FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class PrivacyRuleTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name: str):
        inspector = ProjectInspector(FIXTURES / name)
        report = build_report(inspector.root)
        return {f.rule_id: f for f in privacy.evaluate(inspector, report, self.ruleset)}

    def test_app_privacy_publication_absent_without_evidence_is_unknown(self):
        findings = self._evaluate("review_privacy_unknown")
        finding = findings["REVIEW.PRIVACY.APP_PRIVACY_PUBLICATION"]
        self.assertEqual(finding.status.value, "UNKNOWN")
        self.assertFalse(finding.blocking)
        self.assertTrue(finding.requested_evidence)

    def test_app_privacy_publication_never_auto_declared(self):
        # No fixture provides a `.asc/app_privacy_published.json` attestation file,
        # so every fixture must come back UNKNOWN here -- nothing infers or
        # fabricates a PASS for App Privacy publication.
        for name in ("valid_flutter", "review_valid_basic", "review_login_with_demo_evidence"):
            finding = self._evaluate(name)["REVIEW.PRIVACY.APP_PRIVACY_PUBLICATION"]
            self.assertEqual(finding.status.value, "UNKNOWN")

    def test_permission_declaration_does_not_imply_data_collection(self):
        finding = self._evaluate("valid_flutter")["REVIEW.PRIVACY.PERMISSION_USAGE_DESCRIPTIONS"]
        self.assertEqual(finding.status.value, "PASS")
        lowered = finding.message.lower()
        for claim in ("collects", "collected", "sends data", "tracks the user"):
            self.assertNotIn(claim, lowered)
        self.assertIn("does not imply", lowered)

    def test_permission_usage_description_bridge_never_blocks(self):
        for name in ("valid_flutter", "review_permission_missing_description"):
            finding = self._evaluate(name)["REVIEW.PRIVACY.PERMISSION_USAGE_DESCRIPTIONS"]
            self.assertNotEqual(finding.status.value, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
