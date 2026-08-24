import unittest
from pathlib import Path

from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.report import build_report
from ios_app_store_submit.review.registry import load_ruleset
from ios_app_store_submit.review.rules import review_access

FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class ReviewAccessRuleTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset()

    def _evaluate(self, name: str):
        inspector = ProjectInspector(FIXTURES / name)
        report = build_report(inspector.root)
        return {f.rule_id: f for f in review_access.evaluate(inspector, report, self.ruleset)}

    def test_uncertain_login_is_unknown(self):
        findings = self._evaluate("review_login_uncertain")
        self.assertEqual(findings["REVIEW.ACCESS.LOGIN_REQUIREMENT"].status.value, "UNKNOWN")

    def test_confirmed_login_without_demo_evidence_blocks_with_evidence(self):
        findings = self._evaluate("review_login_without_demo_evidence")
        self.assertEqual(findings["REVIEW.ACCESS.LOGIN_REQUIREMENT"].status.value, "RISK")
        demo = findings["REVIEW.ACCESS.DEMO_CREDENTIALS"]
        self.assertEqual(demo.status.value, "BLOCKED")
        self.assertTrue(demo.evidence)
        self.assertTrue(demo.blocking)

    def test_confirmed_login_with_demo_evidence_is_not_a_false_blocker(self):
        findings = self._evaluate("review_login_with_demo_evidence")
        self.assertEqual(findings["REVIEW.ACCESS.LOGIN_REQUIREMENT"].status.value, "RISK")
        demo = findings["REVIEW.ACCESS.DEMO_CREDENTIALS"]
        self.assertEqual(demo.status.value, "PASS")
        self.assertFalse(demo.blocking)

    def test_login_heuristic_never_blocks_by_itself(self):
        for name in ("review_login_with_demo_evidence", "review_login_without_demo_evidence", "review_login_uncertain"):
            findings = self._evaluate(name)
            self.assertNotEqual(findings["REVIEW.ACCESS.LOGIN_REQUIREMENT"].status.value, "BLOCKED")

    def test_backend_url_existence_is_never_pass(self):
        found = self._evaluate("review_backend_dependency_unknown")["REVIEW.ACCESS.BACKEND_DEPENDENCY"]
        not_found = self._evaluate("review_login_uncertain")["REVIEW.ACCESS.BACKEND_DEPENDENCY"]
        self.assertNotEqual(found.status.value, "PASS")
        self.assertNotEqual(not_found.status.value, "PASS")
        self.assertEqual(found.status.value, "ADVISORY")


if __name__ == "__main__":
    unittest.main()
