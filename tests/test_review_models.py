import unittest

from ios_app_store_submit.readiness.models import Evidence
from ios_app_store_submit.review.models import (
    Confidence, EvaluationType, ReviewFinding, Rule, Ruleset, confidence_from_float,
)


def _rule(**overrides):
    base = dict(
        rule_id="REVIEW.TEST.RULE", apple_guideline="2.1", category="PERFORMANCE", title="t",
        description="d", severity_default="RISK", evaluation_type="RISK_HEURISTIC",
        required_evidence=("x",), fixability="MANUAL", source_url="https://example.com",
        source_last_updated="2026-06-08", confidence_policy="policy",
    )
    base.update(overrides)
    return Rule(**base)


def _finding(**overrides):
    base = dict(
        finding_id="review.test", rule_id="REVIEW.TEST.RULE", apple_guideline="2.1", category="PERFORMANCE",
        status="PASS", confidence="HIGH", message="ok",
    )
    base.update(overrides)
    return ReviewFinding(**base)


class RuleTests(unittest.TestCase):
    def test_heuristic_rule_may_not_default_to_blocked(self):
        with self.assertRaises(ValueError):
            _rule(evaluation_type="RISK_HEURISTIC", severity_default="BLOCKED")

    def test_deterministic_rule_may_default_to_blocked(self):
        rule = _rule(evaluation_type="DETERMINISTIC", severity_default="BLOCKED")
        self.assertEqual(rule.severity_default.value, "BLOCKED")

    def test_evidence_required_rule_may_default_to_blocked(self):
        rule = _rule(evaluation_type="EVIDENCE_REQUIRED", severity_default="BLOCKED")
        self.assertEqual(rule.severity_default.value, "BLOCKED")

    def test_round_trip(self):
        rule = _rule()
        self.assertEqual(Rule.from_dict(rule.to_dict()).to_dict(), rule.to_dict())


class ReviewFindingTests(unittest.TestCase):
    def test_blocked_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            _finding(status="BLOCKED", rule_id="R", apple_guideline="2.1", source_url="https://x",
                     source_last_updated="2026-06-08", ruleset_id="rs")

    def test_blocked_without_provenance_is_rejected(self):
        with self.assertRaises(ValueError):
            _finding(status="BLOCKED", evidence=(Evidence(kind="inspection"),))

    def test_blocked_with_evidence_and_provenance_is_accepted_and_forces_blocking_true(self):
        finding = _finding(status="BLOCKED", evidence=(Evidence(kind="inspection"),), rule_id="R",
                           apple_guideline="2.1", source_url="https://x", source_last_updated="2026-06-08",
                           ruleset_id="rs")
        self.assertTrue(finding.blocking)

    def test_pass_finding_round_trips_through_json_shape(self):
        finding = _finding()
        self.assertEqual(ReviewFinding.from_dict(finding.to_dict()).to_dict(), finding.to_dict())

    def test_confidence_bucketing(self):
        self.assertEqual(confidence_from_float(0.95), Confidence.HIGH)
        self.assertEqual(confidence_from_float(0.7), Confidence.MEDIUM)
        self.assertEqual(confidence_from_float(0.3), Confidence.LOW)


class RulesetTests(unittest.TestCase):
    def test_rule_lookup_and_category_filter(self):
        rule = _rule()
        ruleset = Ruleset(
            ruleset_id="rs", source_name="Apple App Review Guidelines", source_url="https://x",
            source_last_updated="2026-06-08", snapshot_date="2026-08-23", source_language="en",
            schema_version="1.0.0", rules=(rule,),
        )
        self.assertEqual(ruleset.rule("REVIEW.TEST.RULE"), rule)
        self.assertEqual(ruleset.rules_by_category("PERFORMANCE"), (rule,))
        with self.assertRaises(KeyError):
            ruleset.rule("NOT.A.RULE")

    def test_round_trip(self):
        rule = _rule()
        ruleset = Ruleset(
            ruleset_id="rs", source_name="Apple App Review Guidelines", source_url="https://x",
            source_last_updated="2026-06-08", snapshot_date="2026-08-23", source_language="en",
            schema_version="1.0.0", rules=(rule,), future_sources=({"source_name": "HIG"},),
        )
        self.assertEqual(Ruleset.from_dict(ruleset.to_dict()).to_dict(), ruleset.to_dict())


if __name__ == "__main__":
    unittest.main()
