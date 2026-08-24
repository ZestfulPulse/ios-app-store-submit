import unittest
from pathlib import Path

from ios_app_store_submit.review.evaluator import run_pre_review
from ios_app_store_submit.review.provenance import validate_blocked_provenance

FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class ProvenanceGuardTests(unittest.TestCase):
    def _full_provenance(self, **overrides):
        base = dict(
            status="BLOCKED", evidence=["something"], rule_id="R", apple_guideline="2.1",
            source_url="https://example.com", source_last_updated="2026-06-08", ruleset_id="rs-1",
        )
        base.update(overrides)
        return base

    def test_non_blocked_status_is_never_checked(self):
        validate_blocked_provenance(**self._full_provenance(status="PASS", evidence=[], rule_id=None,
                                                              apple_guideline=None, source_url=None,
                                                              source_last_updated=None, ruleset_id=None))

    def test_blocked_with_full_provenance_and_evidence_passes(self):
        validate_blocked_provenance(**self._full_provenance())

    def test_blocked_without_evidence_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_blocked_provenance(**self._full_provenance(evidence=[]))
        self.assertIn("evidence", str(ctx.exception))

    def test_blocked_without_rule_id_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_blocked_provenance(**self._full_provenance(rule_id=None))
        self.assertIn("rule_id", str(ctx.exception))

    def test_blocked_without_apple_guideline_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_blocked_provenance(**self._full_provenance(apple_guideline=""))
        self.assertIn("apple_guideline", str(ctx.exception))

    def test_blocked_without_source_url_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_blocked_provenance(**self._full_provenance(source_url=None))
        self.assertIn("source_url", str(ctx.exception))

    def test_blocked_without_source_last_updated_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_blocked_provenance(**self._full_provenance(source_last_updated=None))
        self.assertIn("source_last_updated", str(ctx.exception))

    def test_blocked_without_ruleset_id_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_blocked_provenance(**self._full_provenance(ruleset_id=None))
        self.assertIn("ruleset_id", str(ctx.exception))


class EveryFindingCarriesFullProvenanceTests(unittest.TestCase):
    def test_review_rule_provenance_fixture_findings_are_fully_provenanced(self):
        result = run_pre_review(FIXTURES / "review_rule_provenance")
        self.assertTrue(result.findings)
        for finding in result.findings:
            self.assertTrue(finding.finding_id)
            self.assertTrue(finding.rule_id)
            self.assertTrue(finding.apple_guideline)
            self.assertTrue(finding.category)
            self.assertTrue(finding.source_url.startswith("https://"))
            self.assertTrue(finding.source_last_updated)
            self.assertEqual(finding.ruleset_id, result.ruleset.ruleset_id)


if __name__ == "__main__":
    unittest.main()
