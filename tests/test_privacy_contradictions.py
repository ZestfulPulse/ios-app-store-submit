import unittest
from pathlib import Path

from ios_app_store_submit.privacy import manifest
from ios_app_store_submit.privacy.contradictions import find_contradictions
from ios_app_store_submit.privacy.models import Confidence, PrivacyEvidence, TriState
from ios_app_store_submit.privacy.report import run_privacy_intelligence
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class ContradictionDetectionTests(unittest.TestCase):
    def test_collection_conflict_is_detected(self):
        evidence = [
            PrivacyEvidence(evidence_id="a", kind="manifest_collected_data_type", source_type="PrivacyInfo.xcprivacy",
                             data_type_candidate="LOCATION", collection=TriState.YES, confidence=Confidence.HIGH,
                             requires_user_confirmation=False),
            PrivacyEvidence(evidence_id="b", kind="local_privacy_answer_attestation",
                             source_type=".asc/app_privacy_answers.json", data_type_candidate="LOCATION",
                             collection=TriState.NO, confidence=Confidence.HIGH, requires_user_confirmation=False),
        ]
        contradictions = find_contradictions(evidence)
        kinds = {c.kind for c in contradictions}
        self.assertIn("COLLECTION_CONFLICT", kinds)

    def test_end_to_end_fixture_produces_contradiction(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_contradicted")
        self.assertTrue(result.contradictions)
        kinds = {c.kind for c in result.contradictions}
        self.assertIn("COLLECTION_CONFLICT", kinds)

    def test_tracking_domain_without_flag_is_a_contradiction(self):
        inspector = ProjectInspector(FIXTURES / "privacy_tracking_domain_conflict")
        _evidence, issues = manifest.inspect(inspector)
        contradictions = find_contradictions([], issues)
        self.assertTrue(any(c.kind == "TRACKING_DOMAIN_WITHOUT_FLAG" for c in contradictions))

    def test_sdk_without_privacy_evidence_is_a_contradiction(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_sdk_analytics_present")
        kinds = {c.kind for c in result.contradictions}
        self.assertIn("SDK_WITHOUT_PRIVACY_EVIDENCE", kinds)


class ContradictionsNotSilentlyResolvedTests(unittest.TestCase):
    def test_contradiction_forces_candidate_state_and_survives_in_report(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_contradicted")
        candidate = next(c for c in result.candidates if c.apple_data_type == "PRECISE_LOCATION")
        self.assertEqual(candidate.state.value, "CONTRADICTED")
        self.assertTrue(candidate.contradictions)
        # The gate must reflect the contradiction; it may never be silently dropped.
        self.assertNotEqual(result.gate, "PASS")
        payload = result.to_dict()
        self.assertTrue(payload["privacy_contradictions"])


class UnresolvedFactsRequireConfirmationTests(unittest.TestCase):
    def test_unknown_collection_requires_confirmation(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_permission_only")
        candidate = result.candidates[0]
        self.assertEqual(candidate.collection.value, "UNKNOWN")
        self.assertTrue(candidate.requires_user_confirmation)
        self.assertTrue(any(q.data_type == candidate.apple_data_type for q in result.questions))

    def test_unknown_tracking_requires_confirmation(self):
        result = run_privacy_intelligence(FIXTURES / "privacy_collection_unknown")
        contacts = result.candidates[0]
        self.assertEqual(contacts.tracking.value, "UNKNOWN")
        self.assertTrue(any(q.data_type == contacts.apple_data_type and "tracking" in q.question.lower()
                            for q in result.questions))


if __name__ == "__main__":
    unittest.main()
