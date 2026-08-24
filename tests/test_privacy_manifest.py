import unittest
from pathlib import Path

from ios_app_store_submit.privacy import manifest
from ios_app_store_submit.privacy.models import TriState
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class ManifestParsingTests(unittest.TestCase):
    def test_valid_manifest_produces_no_structural_issues(self):
        inspector = ProjectInspector(FIXTURES / "privacy_manifest_valid")
        _evidence, issues = manifest.inspect(inspector)
        self.assertEqual(issues, [])

    def test_tracking_boolean_is_parsed(self):
        inspector = ProjectInspector(FIXTURES / "privacy_tracking_true")
        evidence, issues = manifest.inspect(inspector)
        self.assertEqual(issues, [])
        flag = next(e for e in evidence if e.kind == "manifest_tracking_flag")
        self.assertEqual(flag.tracking, TriState.YES)

    def test_tracking_domain_is_parsed_as_evidence(self):
        inspector = ProjectInspector(FIXTURES / "privacy_tracking_true")
        evidence, _issues = manifest.inspect(inspector)
        domains = [e for e in evidence if e.kind == "manifest_tracking_domain"]
        self.assertEqual([e.observed for e in domains], ["doubleclick.net"])

    def test_collected_data_type_is_parsed_with_short_code(self):
        inspector = ProjectInspector(FIXTURES / "privacy_manifest_collection")
        evidence, issues = manifest.inspect(inspector)
        self.assertEqual(issues, [])
        collected = next(e for e in evidence if e.kind == "manifest_collected_data_type")
        self.assertEqual(collected.data_type_candidate, "EMAIL_ADDRESS")
        self.assertEqual(collected.collection, TriState.YES)

    def test_invalid_tracking_type_is_a_deterministic_structural_issue(self):
        inspector = ProjectInspector(FIXTURES / "privacy_manifest_invalid")
        _evidence, issues = manifest.inspect(inspector)
        codes = {issue.code for issue in issues}
        self.assertIn("MANIFEST_INVALID_TRACKING_TYPE", codes)
        self.assertTrue(all(issue.severity.value == "HIGH" for issue in issues if issue.code == "MANIFEST_INVALID_TRACKING_TYPE"))

    def test_tracking_domain_without_flag_is_flagged(self):
        inspector = ProjectInspector(FIXTURES / "privacy_tracking_domain_conflict")
        _evidence, issues = manifest.inspect(inspector)
        codes = {issue.code for issue in issues}
        self.assertIn("MANIFEST_TRACKING_DOMAIN_WITHOUT_FLAG", codes)

    def test_unknown_data_type_identifier_is_flagged(self):
        inspector = ProjectInspector(FIXTURES / "privacy_manifest_collection")
        data = {"NSPrivacyCollectedDataTypes": [{"NSPrivacyCollectedDataType": "NotARealAppleType"}]}
        _evidence, issues = manifest._validate_manifest(
            "PrivacyInfo.xcprivacy", data, manifest.COLLECTED_DATA_TYPE_SHORT_CODES,
        )
        self.assertTrue(any(issue.code == "MANIFEST_UNKNOWN_DATA_TYPE" for issue in issues))

    def test_duplicate_data_type_is_flagged(self):
        entry = {"NSPrivacyCollectedDataType": "NSPrivacyCollectedDataTypeEmailAddress"}
        data = {"NSPrivacyCollectedDataTypes": [entry, dict(entry)]}
        _evidence, issues = manifest._validate_manifest(
            "PrivacyInfo.xcprivacy", data, manifest.COLLECTED_DATA_TYPE_SHORT_CODES,
        )
        self.assertTrue(any(issue.code == "MANIFEST_DUPLICATE_DATA_TYPE" for issue in issues))


class RequiredReasonApiTests(unittest.TestCase):
    def test_detected_api_with_matching_manifest_reason_is_not_blocked(self):
        inspector = ProjectInspector(FIXTURES / "privacy_required_reason_present")
        manifest_evidence, _issues = manifest.inspect(inspector)
        _rr_evidence, rr_issues = manifest.inspect_required_reason_apis(inspector, manifest_evidence)
        self.assertEqual(rr_issues, [])

    def test_detected_api_without_manifest_reason_is_deterministic_blocker(self):
        inspector = ProjectInspector(FIXTURES / "privacy_required_reason_missing")
        manifest_evidence, _issues = manifest.inspect(inspector)
        _rr_evidence, rr_issues = manifest.inspect_required_reason_apis(inspector, manifest_evidence)
        codes = {issue.code for issue in rr_issues}
        self.assertIn("MANIFEST_REASON_MISSING", codes)
        self.assertTrue(all(issue.severity.value == "HIGH" for issue in rr_issues))

    def test_incomplete_detection_remains_unknown_not_blocked(self):
        inspector = ProjectInspector(FIXTURES / "privacy_manifest_valid")
        manifest_evidence, _issues = manifest.inspect(inspector)
        rr_evidence, rr_issues = manifest.inspect_required_reason_apis(inspector, manifest_evidence)
        self.assertEqual(rr_issues, [])
        unverified = next(e for e in rr_evidence if e.kind == "required_reason_unverified")
        self.assertEqual(unverified.confidence.value, "LOW")
        self.assertTrue(unverified.requires_user_confirmation)


if __name__ == "__main__":
    unittest.main()
