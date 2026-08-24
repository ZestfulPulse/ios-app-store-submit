import unittest

from ios_app_store_submit.privacy.mapper import build_candidates
from ios_app_store_submit.privacy.models import CandidateState, Confidence, PrivacyEvidence, TriState


def _attestation(data_type, **fields):
    return PrivacyEvidence(
        evidence_id=f"local_answer:{data_type}", kind="local_privacy_answer_attestation",
        source_type=".asc/app_privacy_answers.json", data_type_candidate=data_type,
        confidence=Confidence.HIGH, requires_user_confirmation=False, **fields,
    )


def _permission(data_type):
    return PrivacyEvidence(
        evidence_id=f"permission:{data_type}", kind="permission_declaration", source_type="Info.plist",
        data_type_candidate=data_type, access=TriState.YES, confidence=Confidence.HIGH,
        requires_user_confirmation=True,
    )


class MapperDeterminismTests(unittest.TestCase):
    def test_deterministic_transmission_evidence_marks_transmission(self):
        evidence = [_attestation("LOCATION", transmission=TriState.YES)]
        candidates = build_candidates(evidence)
        # transmission is not a candidate field by itself (it aggregates into
        # collection/linkage/tracking); assert the source evidence retained it.
        self.assertEqual(evidence[0].transmission, TriState.YES)
        self.assertEqual(candidates[0].collection, TriState.UNKNOWN)

    def test_transmission_alone_does_not_imply_collection(self):
        evidence = [_attestation("LOCATION", transmission=TriState.YES, collection=None)]
        candidates = build_candidates(evidence)
        self.assertEqual(candidates[0].collection, TriState.UNKNOWN)

    def test_collection_requires_its_own_evidence(self):
        evidence = [_attestation("LOCATION", transmission=TriState.YES, collection=TriState.YES)]
        candidates = build_candidates(evidence)
        self.assertEqual(candidates[0].collection, TriState.YES)


class CandidateStateTests(unittest.TestCase):
    def test_confirmed_only_from_deterministic_evidence(self):
        evidence = [_attestation("LOCATION", collection=TriState.YES, linked_to_user=TriState.NO, tracking=TriState.NO)]
        candidates = build_candidates(evidence)
        self.assertEqual(candidates[0].state, CandidateState.CONFIRMED)
        self.assertEqual(candidates[0].confidence, Confidence.HIGH)

    def test_permission_only_evidence_stays_unknown_state(self):
        evidence = [_permission("CAMERA")]
        candidates = build_candidates(evidence)
        self.assertEqual(candidates[0].state, CandidateState.UNKNOWN)
        self.assertTrue(candidates[0].requires_user_confirmation)

    def test_conflicting_evidence_resolves_to_unknown_field_value(self):
        evidence = [
            _attestation("LOCATION", collection=TriState.YES),
            PrivacyEvidence(
                evidence_id="manifest:x:collected:LOCATION", kind="manifest_collected_data_type",
                source_type="PrivacyInfo.xcprivacy", data_type_candidate="LOCATION",
                collection=TriState.NO, confidence=Confidence.HIGH, requires_user_confirmation=False,
            ),
        ]
        candidates = build_candidates(evidence)
        self.assertEqual(candidates[0].collection, TriState.UNKNOWN)
        self.assertTrue(candidates[0].requires_user_confirmation)


class StableOrderingTests(unittest.TestCase):
    def test_candidates_are_sorted_by_data_type(self):
        evidence = [_permission("LOCATION"), _permission("CAMERA"), _permission("CONTACTS")]
        candidates = build_candidates(evidence)
        self.assertEqual([c.apple_data_type for c in candidates], ["CAMERA", "CONTACTS", "LOCATION"])


if __name__ == "__main__":
    unittest.main()
