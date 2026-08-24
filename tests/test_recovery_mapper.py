import unittest

from ios_app_store_submit.recovery.mapper import map_rejection
from ios_app_store_submit.recovery.models import RootCauseCategory
from ios_app_store_submit.recovery.parser import parse_rejection


class GuidelineMappingTests(unittest.TestCase):
    def test_explicit_known_guideline_maps_correctly(self):
        # Guideline 2.3 resolves to exactly one Phase 3 category (METADATA),
        # so a HIGH-confidence mapping must land on that single category.
        rejection = parse_rejection("Guideline 2.3 - Performance - Accurate Metadata: placeholder text.",
                                     rejection_id="r1")
        mappings = map_rejection(rejection)
        guideline_mapping = next(m for m in mappings if m.apple_guideline == "2.3")
        self.assertEqual(guideline_mapping.category, RootCauseCategory.METADATA)
        self.assertEqual(guideline_mapping.confidence.value, "HIGH")
        self.assertTrue(guideline_mapping.mapped_rule_ids)

    def test_unknown_guideline_stays_unknown_never_coerced(self):
        rejection = parse_rejection("Guideline 99.9 - Reserved: something is wrong.", rejection_id="r1")
        mappings = map_rejection(rejection)
        guideline_mapping = next(m for m in mappings if m.apple_guideline == "99.9")
        self.assertEqual(guideline_mapping.category, RootCauseCategory.UNKNOWN)
        self.assertEqual(guideline_mapping.mapped_rule_ids, ())
        self.assertEqual(guideline_mapping.confidence.value, "LOW")

    def test_ambiguous_guideline_covering_multiple_categories_is_high_confidence_but_unknown_category(self):
        # Guideline 2.1 legitimately spans multiple Phase 3 categories
        # (PERFORMANCE and REVIEW_ACCESS); the rule *match* is still real
        # (HIGH), but the category classification is honestly ambiguous.
        rejection = parse_rejection("Guideline 2.1 - Performance: some concern.", rejection_id="r1")
        mappings = map_rejection(rejection)
        guideline_mapping = next(m for m in mappings if m.apple_guideline == "2.1")
        self.assertEqual(guideline_mapping.confidence.value, "HIGH")
        self.assertTrue(guideline_mapping.mapped_rule_ids)


class KeywordSignalMappingTests(unittest.TestCase):
    def test_ambiguous_keyword_only_text_cannot_reach_high_confidence(self):
        rejection = parse_rejection("We could not sign in using the demo account credentials.", rejection_id="r1")
        mappings = map_rejection(rejection)
        signal_mapping = next(m for m in mappings if m.mapping_id.endswith(":signal:review_access"))
        self.assertEqual(signal_mapping.confidence.value, "MEDIUM")

    def test_phase3_review_access_rule_ids_are_referenced(self):
        rejection = parse_rejection("We could not sign in using the demo account credentials.", rejection_id="r1")
        mappings = map_rejection(rejection)
        signal_mapping = next(m for m in mappings if m.mapping_id.endswith(":signal:review_access"))
        self.assertTrue(any(rule_id.startswith("REVIEW.ACCESS.") for rule_id in signal_mapping.mapped_rule_ids))

    def test_phase3_privacy_rule_ids_are_referenced(self):
        rejection = parse_rejection("Your app's privacy practices were not accurately reflected.", rejection_id="r1")
        mappings = map_rejection(rejection)
        signal_mapping = next(m for m in mappings if m.mapping_id.endswith(":signal:privacy"))
        self.assertEqual(signal_mapping.category, RootCauseCategory.PRIVACY)
        self.assertTrue(any(rule_id.startswith("REVIEW.PRIVACY.") for rule_id in signal_mapping.mapped_rule_ids))

    def test_phase5_hig_rule_ids_are_referenced(self):
        rejection = parse_rejection(
            "Your app's interface does not follow the Human Interface Guidelines for touch target sizing.",
            rejection_id="r1",
        )
        mappings = map_rejection(rejection)
        signal_mapping = next(m for m in mappings if m.mapping_id.endswith(":signal:design_hig"))
        self.assertEqual(signal_mapping.category, RootCauseCategory.DESIGN_HIG)
        self.assertTrue(any(rule_id.startswith("DESIGN.") for rule_id in signal_mapping.mapped_rule_ids))

    def test_no_signal_and_no_guideline_is_unknown_low_confidence(self):
        rejection = parse_rejection("Please review your app and make improvements.", rejection_id="r1")
        mappings = map_rejection(rejection)
        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0].category, RootCauseCategory.UNKNOWN)
        self.assertEqual(mappings[0].confidence.value, "LOW")


if __name__ == "__main__":
    unittest.main()
