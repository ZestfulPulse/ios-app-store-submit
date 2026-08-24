import unittest
from unittest import mock

from ios_app_store_submit.design.models import EvaluationType, Status, load_ruleset


class RegistryTests(unittest.TestCase):
    def test_registry_loads_offline_with_no_network_access(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network access attempted")):
            ruleset = load_ruleset()
        self.assertTrue(ruleset.rules)

    def test_source_last_updated_is_2026_06_08(self):
        ruleset = load_ruleset()
        self.assertEqual(ruleset.source_last_updated, "2026-06-08")
        for rule in ruleset.rules:
            self.assertEqual(rule.source_last_updated, "2026-06-08")

    def test_ruleset_metadata_fields_present(self):
        ruleset = load_ruleset()
        self.assertTrue(ruleset.ruleset_id)
        self.assertEqual(ruleset.source_name, "Apple Human Interface Guidelines")
        self.assertTrue(ruleset.source_url.startswith("https://developer.apple.com/"))
        self.assertTrue(ruleset.snapshot_date)
        self.assertEqual(ruleset.source_language, "en")
        self.assertTrue(ruleset.schema_version)

    def test_every_rule_has_source_provenance(self):
        ruleset = load_ruleset()
        for rule in ruleset.rules:
            self.assertTrue(rule.hig_area, rule.rule_id)
            self.assertTrue(rule.source_url.startswith("https://"), rule.rule_id)
            self.assertTrue(rule.source_last_updated, rule.rule_id)
            self.assertTrue(rule.confidence_policy, rule.rule_id)

    def test_no_heuristic_rule_defaults_to_blocked(self):
        ruleset = load_ruleset()
        for rule in ruleset.rules:
            if rule.evaluation_type is EvaluationType.RISK_HEURISTIC:
                self.assertNotEqual(rule.severity_default, Status.BLOCKED, rule.rule_id)

    def test_four_phase5_areas_are_represented(self):
        ruleset = load_ruleset()
        areas = {rule.hig_area for rule in ruleset.rules}
        self.assertEqual(areas, {"ACCESSIBILITY", "LAYOUT", "LOCALIZATION", "INTERACTION"})

    def test_future_sources_are_documentation_only(self):
        ruleset = load_ruleset()
        visual = next(item for item in ruleset.future_sources if "Visual" in item["source_name"])
        self.assertEqual(visual["status"], "not_yet_implemented")


if __name__ == "__main__":
    unittest.main()
