import unittest
from pathlib import Path

from ios_app_store_submit.readiness.gates.reviewability import inspect_reviewability
from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.models import Status


FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class ReviewabilityGateTests(unittest.TestCase):
    def test_login_without_review_info_is_blocked_with_evidence(self):
        result = inspect_reviewability(ProjectInspector(FIXTURES / "missing_review_info"))
        finding = next(item for item in result.findings if item.rule_id == "REVIEW_INFO")
        self.assertEqual(finding.status, Status.BLOCKED)
        self.assertTrue(finding.evidence)

    def test_login_is_conservative_when_not_established(self):
        result = inspect_reviewability(ProjectInspector(FIXTURES / "valid_flutter"))
        finding = next(item for item in result.findings if item.rule_id == "LOGIN")
        self.assertEqual(finding.status, Status.UNKNOWN)

    def test_credentials_in_config_are_not_review_access_evidence(self):
        # username:/password: keys in ordinary config are app/runtime credentials,
        # not a documented account for App Review. They must not satisfy the
        # Guideline 2.1 demo-account requirement (see the comment above the regex).
        result = inspect_reviewability(ProjectInspector(FIXTURES / "review_login_credentials_config_only"))
        finding = next(item for item in result.findings if item.rule_id == "REVIEW_INFO")
        self.assertEqual(finding.status, Status.BLOCKED)
        self.assertTrue(finding.blocking)
