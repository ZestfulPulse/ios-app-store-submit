import unittest
from pathlib import Path

from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.report import build_report
from ios_app_store_submit.review.registry import load_ruleset
from ios_app_store_submit.review.rules import performance

FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class PerformanceRuleTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name: str):
        inspector = ProjectInspector(FIXTURES / name)
        report = build_report(inspector.root)
        return {f.rule_id: f for f in performance.evaluate(inspector, report, self.ruleset)}

    def test_valid_project_passes_completeness_checks(self):
        findings = self._evaluate("valid_flutter")
        self.assertEqual(findings["REVIEW.PERFORMANCE.PROJECT_STRUCTURE"].status.value, "PASS")
        self.assertEqual(findings["REVIEW.PERFORMANCE.VERSION_BUILD"].status.value, "PASS")

    def test_missing_version_entry_blocks_version_build_with_evidence(self):
        findings = self._evaluate("missing_version")
        finding = findings["REVIEW.PERFORMANCE.VERSION_BUILD"]
        self.assertEqual(finding.status.value, "BLOCKED")
        self.assertTrue(finding.evidence)
        self.assertTrue(finding.blocking)
        # pubspec.yaml, Info.plist, and the Xcode project all still exist here,
        # so structural presence itself is unaffected by the missing version.
        self.assertEqual(findings["REVIEW.PERFORMANCE.PROJECT_STRUCTURE"].status.value, "PASS")

    def test_placeholder_scan_is_never_blocked(self):
        for name in ("valid_flutter", "review_placeholder_metadata"):
            findings = self._evaluate(name)
            self.assertNotEqual(findings["REVIEW.PERFORMANCE.PLACEHOLDER_CONFIG"].status.value, "BLOCKED")

    def test_permission_dependency_without_usage_description_blocks_with_evidence(self):
        findings = self._evaluate("review_permission_missing_description")
        finding = findings["REVIEW.PERFORMANCE.PERMISSION_DESCRIPTIONS"]
        self.assertEqual(finding.status.value, "BLOCKED")
        self.assertTrue(finding.evidence)
        self.assertTrue(finding.blocking)

    def test_permission_dependency_with_usage_description_passes(self):
        findings = self._evaluate("valid_flutter")
        self.assertEqual(findings["REVIEW.PERFORMANCE.PERMISSION_DESCRIPTIONS"].status.value, "PASS")

    def test_no_known_dependency_passes_without_claiming_it_was_checked_deeply(self):
        findings = self._evaluate("review_login_uncertain")
        self.assertEqual(findings["REVIEW.PERFORMANCE.PERMISSION_DESCRIPTIONS"].status.value, "PASS")


if __name__ == "__main__":
    unittest.main()
