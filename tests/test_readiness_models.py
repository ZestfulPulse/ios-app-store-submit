import unittest

from ios_app_store_submit.readiness.models import Evidence, Finding, Fixability, Status


class ReadinessModelTests(unittest.TestCase):
    def test_blocked_requires_evidence(self):
        with self.assertRaises(ValueError):
            Finding("x", "TECHNICAL", "X", "x", Status.BLOCKED, "blocked", (), None, 1.0, Fixability.MANUAL, "fix")

    def test_unknown_is_not_pass(self):
        self.assertNotEqual(Status.UNKNOWN, Status.PASS)
        finding = Finding("x", "METADATA", "X", "x", Status.UNKNOWN, "unknown", (Evidence("inspection"),))
        self.assertEqual(finding.status, Status.UNKNOWN)

    def test_evidence_round_trip(self):
        evidence = Evidence("plist", path="ios/Runner/Info.plist", key="CFBundleName", observed="Demo")
        self.assertEqual(Evidence.from_dict(evidence.to_dict()), evidence)
