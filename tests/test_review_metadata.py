import unittest
from pathlib import Path

from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.report import build_report
from ios_app_store_submit.review.registry import load_ruleset
from ios_app_store_submit.review.rules import metadata

FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class MetadataRuleTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name: str):
        inspector = ProjectInspector(FIXTURES / name)
        report = build_report(inspector.root)
        return {f.rule_id: f for f in metadata.evaluate(inspector, report, self.ruleset)}

    def test_exact_review_facing_placeholder_is_blocked_with_evidence(self):
        findings = self._evaluate("review_placeholder_metadata")
        finding = findings["REVIEW.METADATA.PLACEHOLDER_STRINGS"]
        self.assertEqual(finding.status.value, "BLOCKED")
        self.assertTrue(finding.evidence)
        self.assertTrue(finding.blocking)
        self.assertIn("CFBundleDisplayName", finding.message)

    def test_valid_project_has_no_placeholder_finding(self):
        findings = self._evaluate("valid_flutter")
        self.assertEqual(findings["REVIEW.METADATA.PLACEHOLDER_STRINGS"].status.value, "PASS")

    def test_missing_url_candidates_are_unknown_not_blocked(self):
        findings = self._evaluate("missing_privacy_policy")
        finding = findings["REVIEW.METADATA.PRIVACY_URL_CANDIDATE"]
        self.assertEqual(finding.status.value, "UNKNOWN")
        self.assertFalse(finding.blocking)

    def test_display_name_and_version_bridge_readiness_findings(self):
        findings = self._evaluate("valid_flutter")
        self.assertEqual(findings["REVIEW.METADATA.DISPLAY_NAME"].status.value, "PASS")
        self.assertEqual(findings["REVIEW.METADATA.VERSION_COHERENT"].status.value, "PASS")

    def test_localization_consistency_is_never_blocking(self):
        for name in ("valid_flutter", "missing_version"):
            findings = self._evaluate(name)
            self.assertFalse(findings["REVIEW.METADATA.LOCALIZATION_CONSISTENCY"].blocking)


if __name__ == "__main__":
    unittest.main()
