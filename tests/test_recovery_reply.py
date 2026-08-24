import unittest
from pathlib import Path

from ios_app_store_submit.recovery.models import (
    ClaimStatus, RootCauseCandidate, RootCauseCategory, RootCauseStatus, VerificationResult,
)
from ios_app_store_submit.recovery.parser import parse_rejection
from ios_app_store_submit.recovery.reply import draft_reply
from ios_app_store_submit.recovery.report import run_recovery
from ios_app_store_submit.readiness.models import Evidence
from ios_app_store_submit.review.models import Confidence


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "recovery"


def candidate(category, status=RootCauseStatus.CONFIRMED, *, root_id="rc:test"):
    return RootCauseCandidate(
        root_cause_id=root_id, rejection_id="r1", category=category, title="Review issue",
        hypothesis="hypothesis", confidence=Confidence.HIGH,
        evidence=(Evidence(kind="text", observed="local evidence"),), missing_evidence=(),
        related_findings=(), source_paths=(), requires_runtime=False,
        requires_user_confirmation=False, status=status,
    )


def verification(root_id, status, pending_reason=None):
    return VerificationResult(
        verification_id=f"verify:{root_id}", root_cause_id=root_id, claim_status=status,
        pending_reason=pending_reason, rechecked_rule_ids=(), message="verification", evidence=(),
    )


class ReplyClaimGateTests(unittest.TestCase):
    def test_verified_claim_may_say_fixed(self):
        result = run_recovery(FIXTURES / "reject_fixed_verified", FIXTURES / "reject_fixed_verified" / "rejection.txt")
        self.assertTrue(any(item.status is ClaimStatus.VERIFIED for item in result.reply_draft.claims))
        self.assertIn("fixed", result.reply_draft.body.lower())

    def test_user_attested_fact_is_stated_as_user_confirmed(self):
        result = run_recovery(
            FIXTURES / "reject_demo_credentials_user_attested",
            FIXTURES / "reject_demo_credentials_user_attested" / "rejection.txt",
        )
        self.assertEqual(result.reply_draft.claims[0].status, ClaimStatus.USER_ATTESTED)
        self.assertIn("developer has confirmed", result.reply_draft.body.lower())

    def test_unverified_claim_cannot_use_any_resolution_phrase(self):
        result = run_recovery(FIXTURES / "reject_fixed_unverified", FIXTURES / "reject_fixed_unverified" / "rejection.txt")
        self.assertEqual(result.reply_draft.claims[0].status, ClaimStatus.UNVERIFIED)
        lowered = result.reply_draft.body.lower()
        for phrase in (
            "we fixed", "we resolved", "we corrected", "the issue has been fixed",
            "the issue has been resolved",
        ):
            self.assertNotIn(phrase, lowered)
        self.assertFalse(result.reply_draft.ready_to_send)

    def test_claim_wording_is_structural_not_phrase_scan_only(self):
        rejection = parse_rejection("A reviewer reported a concern.", rejection_id="r1")
        root = candidate(RootCauseCategory.METADATA, RootCauseStatus.UNKNOWN)
        result = draft_reply(rejection, [root], [verification("rc:test", ClaimStatus.UNVERIFIED)])
        claim = result.claims[0]
        self.assertIn("clarification", claim.statement.lower())
        self.assertNotIn("we fixed", claim.statement.lower())

    def test_clarification_mode(self):
        result = run_recovery(
            FIXTURES / "reject_ambiguous_text", FIXTURES / "reject_ambiguous_text" / "rejection.txt",
        )
        self.assertEqual(result.reply_draft.response_mode.value, "CLARIFICATION")
        self.assertFalse(result.reply_draft.ready_to_send)

    def test_partially_fixed_mode(self):
        result = run_recovery(FIXTURES / "reject_partial_fix", FIXTURES / "reject_partial_fix" / "rejection.txt")
        self.assertEqual(result.reply_draft.response_mode.value, "PARTIALLY_FIXED")
        self.assertFalse(result.reply_draft.ready_to_send)

    def test_dispute_with_evidence_mode(self):
        result = run_recovery(
            FIXTURES / "reject_dispute_with_evidence",
            FIXTURES / "reject_dispute_with_evidence" / "rejection.txt",
        )
        self.assertEqual(result.reply_draft.response_mode.value, "DISPUTE_WITH_EVIDENCE")
        self.assertTrue(result.reply_draft.ready_to_send)
        self.assertIn("satisfies the cited guideline", result.reply_draft.body)

    def test_unresolved_contradiction_blocks_ready_to_send(self):
        rejection = parse_rejection("Guideline 2.3 concern.", rejection_id="r1")
        root = candidate(RootCauseCategory.METADATA, RootCauseStatus.CONTRADICTED)
        draft = draft_reply(rejection, [root], [verification("rc:test", ClaimStatus.UNVERIFIED)])
        self.assertFalse(draft.ready_to_send)
        self.assertEqual(draft.response_mode.value, "CLARIFICATION")

    def test_credentials_privacy_and_reviewer_facts_are_not_fabricated(self):
        rejection = parse_rejection(
            "username: demo@example.com password: super-secret. App Privacy answers are needed; "
            "the reviewer did not provide device details.", rejection_id="facts",
        )
        root = candidate(RootCauseCategory.UNKNOWN, RootCauseStatus.UNKNOWN, root_id="rc:facts")
        draft = draft_reply(rejection, [root], [verification("rc:facts", ClaimStatus.UNVERIFIED)])
        lowered = draft.body.lower()
        for secret in ("demo@example.com", "super-secret"):
            self.assertNotIn(secret, draft.body)
        self.assertNotIn("we collect", lowered)
        self.assertNotIn("we do not collect", lowered)
        self.assertNotIn("we tested on", lowered)
        self.assertNotIn("we provided", lowered)
        self.assertIn("[REDACTED]", draft.body)


if __name__ == "__main__":
    unittest.main()
