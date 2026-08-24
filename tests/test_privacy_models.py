import unittest

from ios_app_store_submit.privacy.models import (
    CandidateState, Confidence, Contradiction, PrivacyCandidate, PrivacyEvidence,
    Severity, TriState, UserConfirmationQuestion, tri_state,
)


class TriStateTests(unittest.TestCase):
    def test_none_is_unknown(self):
        self.assertEqual(tri_state(None), TriState.UNKNOWN)

    def test_bool_maps_to_yes_no(self):
        self.assertEqual(tri_state(True), TriState.YES)
        self.assertEqual(tri_state(False), TriState.NO)

    def test_string_round_trips(self):
        self.assertEqual(tri_state("YES"), TriState.YES)
        self.assertEqual(tri_state("no"), TriState.NO)


class PrivacyEvidenceTests(unittest.TestCase):
    def test_defaults_to_unknown_tri_states(self):
        evidence = PrivacyEvidence(evidence_id="e1", kind="test", source_type="test")
        self.assertEqual(evidence.access, TriState.UNKNOWN)
        self.assertEqual(evidence.transmission, TriState.UNKNOWN)
        self.assertEqual(evidence.collection, TriState.UNKNOWN)
        self.assertEqual(evidence.linked_to_user, TriState.UNKNOWN)
        self.assertEqual(evidence.tracking, TriState.UNKNOWN)

    def test_round_trip(self):
        evidence = PrivacyEvidence(
            evidence_id="e1", kind="permission_declaration", source_type="Info.plist",
            observed="x", data_type_candidate="LOCATION", access=TriState.YES,
            confidence=Confidence.HIGH, purpose_candidates=("APP_FUNCTIONALITY",),
        )
        self.assertEqual(PrivacyEvidence.from_dict(evidence.to_dict()).to_dict(), evidence.to_dict())


class PrivacyCandidateTests(unittest.TestCase):
    def test_confirmed_requires_high_confidence(self):
        with self.assertRaises(ValueError):
            PrivacyCandidate(
                candidate_id="c1", apple_data_type="LOCATION", state=CandidateState.CONFIRMED,
                confidence=Confidence.MEDIUM,
            )

    def test_confirmed_with_high_confidence_is_accepted(self):
        candidate = PrivacyCandidate(
            candidate_id="c1", apple_data_type="LOCATION", state=CandidateState.CONFIRMED,
            confidence=Confidence.HIGH,
        )
        self.assertEqual(candidate.state, CandidateState.CONFIRMED)

    def test_round_trip(self):
        candidate = PrivacyCandidate(
            candidate_id="c1", apple_data_type="LOCATION", state=CandidateState.UNKNOWN,
            evidence_ids=("e1", "e2"), contradictions=("k1",),
        )
        self.assertEqual(PrivacyCandidate.from_dict(candidate.to_dict()).to_dict(), candidate.to_dict())


class ContradictionTests(unittest.TestCase):
    def test_round_trip(self):
        contradiction = Contradiction(
            contradiction_id="k1", kind="COLLECTION_CONFLICT", severity=Severity.HIGH,
            evidence_left="e1", evidence_right="e2", message="m", requested_resolution="r",
        )
        self.assertEqual(Contradiction.from_dict(contradiction.to_dict()).to_dict(), contradiction.to_dict())


class UserConfirmationQuestionTests(unittest.TestCase):
    def test_default_allowed_answers_are_tri_state(self):
        question = UserConfirmationQuestion(
            question_id="q1", data_type="LOCATION", question="?", why_needed="because",
        )
        self.assertEqual(question.allowed_answers, ("YES", "NO", "UNKNOWN"))

    def test_round_trip(self):
        question = UserConfirmationQuestion(
            question_id="q1", data_type="LOCATION", question="?", why_needed="because",
            evidence_ids=("e1",), answer_type="MULTI_SELECT", allowed_answers=("A", "B"),
        )
        self.assertEqual(UserConfirmationQuestion.from_dict(question.to_dict()).to_dict(), question.to_dict())


if __name__ == "__main__":
    unittest.main()
