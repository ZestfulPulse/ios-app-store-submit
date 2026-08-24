import unittest

from ios_app_store_submit.design.models import (
    Confidence, DesignEvidence, DesignFinding, EvaluationType, Rule, Ruleset,
)


def _rule(**overrides):
    base = dict(
        rule_id="DESIGN.TEST.RULE", hig_area="ACCESSIBILITY", title="t", description="d",
        severity_default="RISK", evaluation_type="RISK_HEURISTIC", required_evidence=("x",),
        fixability="MANUAL", source_url="https://example.com", source_last_updated="2026-06-08",
        confidence_policy="policy",
    )
    base.update(overrides)
    return Rule(**base)


def _finding(**overrides):
    base = dict(
        finding_id="design.test", rule_id="DESIGN.TEST.RULE", hig_area="ACCESSIBILITY",
        title="t", status="PASS", confidence="HIGH", message="ok", check_type="RISK_HEURISTIC",
    )
    base.update(overrides)
    return DesignFinding(**base)


class RuleTests(unittest.TestCase):
    def test_heuristic_rule_may_not_default_to_blocked(self):
        with self.assertRaises(ValueError):
            _rule(evaluation_type="RISK_HEURISTIC", severity_default="BLOCKED")

    def test_deterministic_rule_may_default_to_blocked(self):
        rule = _rule(evaluation_type="DETERMINISTIC", severity_default="BLOCKED")
        self.assertEqual(rule.severity_default.value, "BLOCKED")

    def test_round_trip(self):
        rule = _rule()
        self.assertEqual(Rule.from_dict(rule.to_dict()).to_dict(), rule.to_dict())


class DesignFindingTests(unittest.TestCase):
    def test_heuristic_finding_cannot_block(self):
        with self.assertRaises(ValueError):
            _finding(status="BLOCKED", check_type="RISK_HEURISTIC",
                     evidence=(DesignEvidence(kind="inspection"),), rule_id="R",
                     source_url="https://x", ruleset_id="rs")

    def test_blocked_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            _finding(status="BLOCKED", check_type="DETERMINISTIC", rule_id="R",
                     source_url="https://x", ruleset_id="rs")

    def test_blocked_without_provenance_is_rejected(self):
        with self.assertRaises(ValueError):
            _finding(status="BLOCKED", check_type="DETERMINISTIC",
                     evidence=(DesignEvidence(kind="inspection"),))

    def test_blocked_with_evidence_and_provenance_is_accepted_and_forces_blocking_true(self):
        finding = _finding(status="BLOCKED", check_type="DETERMINISTIC",
                           evidence=(DesignEvidence(kind="inspection"),), rule_id="R",
                           source_url="https://x", ruleset_id="rs")
        self.assertTrue(finding.blocking)

    def test_unknown_is_not_pass(self):
        finding = _finding(status="UNKNOWN", confidence="LOW")
        self.assertNotEqual(finding.status.value, "PASS")

    def test_round_trip(self):
        finding = _finding()
        self.assertEqual(DesignFinding.from_dict(finding.to_dict()).to_dict(), finding.to_dict())


class DesignEvidenceTests(unittest.TestCase):
    def test_runtime_required_is_explicit(self):
        evidence = DesignEvidence(kind="inspection", runtime_required=True)
        self.assertTrue(evidence.to_dict()["runtime_required"])
        self.assertFalse(evidence.to_dict()["screenshot_required"])

    def test_round_trip(self):
        evidence = DesignEvidence(kind="fixed_size", source_path="lib/main.dart", line=3, symbol="k",
                                   observed="20x20", expected=">=44x44", parser="regex",
                                   confidence=Confidence.HIGH, runtime_required=True, screenshot_required=True)
        self.assertEqual(DesignEvidence.from_dict(evidence.to_dict()).to_dict(), evidence.to_dict())


class RulesetTests(unittest.TestCase):
    def test_rule_lookup_and_area_filter(self):
        rule = _rule()
        ruleset = Ruleset(
            ruleset_id="rs", source_name="Apple Human Interface Guidelines", source_url="https://x",
            source_last_updated="2026-06-08", snapshot_date="2026-08-23", source_language="en",
            schema_version="1.0.0", rules=(rule,),
        )
        self.assertEqual(ruleset.rule("DESIGN.TEST.RULE"), rule)
        self.assertEqual(ruleset.rules_by_area("ACCESSIBILITY"), (rule,))
        with self.assertRaises(KeyError):
            ruleset.rule("NOT.A.RULE")

    def test_round_trip(self):
        rule = _rule()
        ruleset = Ruleset(
            ruleset_id="rs", source_name="Apple Human Interface Guidelines", source_url="https://x",
            source_last_updated="2026-06-08", snapshot_date="2026-08-23", source_language="en",
            schema_version="1.0.0", rules=(rule,), future_sources=({"source_name": "Visual Evidence"},),
        )
        self.assertEqual(Ruleset.from_dict(ruleset.to_dict()).to_dict(), ruleset.to_dict())


if __name__ == "__main__":
    unittest.main()
