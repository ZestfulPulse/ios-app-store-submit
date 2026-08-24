import unittest

from ios_app_store_submit.readiness.models import Evidence
from ios_app_store_submit.recovery.models import (
    Claim, ClaimStatus, RecoveryFixPlan, RejectionMessage, RejectionSource, ReplyDraft,
    RootCauseCandidate, RootCauseCategory, RootCauseStatus, RuleMapping, Safety, VerificationResult,
)


class RejectionMessageTests(unittest.TestCase):
    def test_round_trip(self):
        rejection = RejectionMessage(
            rejection_id="r1", source=RejectionSource.MANUAL_TEXT, received_at="2026-08-23", raw_text="text",
            guideline_refs=("2.1",), attachments=("shot.png",), metadata={"signals": {"privacy": ["privacy"]}},
        )
        self.assertEqual(RejectionMessage.from_dict(rejection.to_dict()).to_dict(), rejection.to_dict())


class RuleMappingTests(unittest.TestCase):
    def test_high_confidence_requires_mapped_rule_ids(self):
        with self.assertRaises(ValueError):
            RuleMapping(
                mapping_id="m1", rejection_id="r1", apple_guideline="99.9", mapped_rule_ids=(),
                category=RootCauseCategory.UNKNOWN, confidence="HIGH", evidence=(Evidence(kind="text"),),
                mapping_reason="x",
            )

    def test_round_trip(self):
        mapping = RuleMapping(
            mapping_id="m1", rejection_id="r1", apple_guideline="2.1", mapped_rule_ids=("REVIEW.ACCESS.X",),
            category=RootCauseCategory.REVIEW_ACCESS, confidence="HIGH", evidence=(Evidence(kind="text"),),
            mapping_reason="x",
        )
        self.assertEqual(RuleMapping.from_dict(mapping.to_dict()).to_dict(), mapping.to_dict())


class RootCauseCandidateTests(unittest.TestCase):
    def test_confirmed_requires_evidence(self):
        with self.assertRaises(ValueError):
            RootCauseCandidate(
                root_cause_id="rc1", rejection_id="r1", category=RootCauseCategory.REVIEW_ACCESS, title="t",
                hypothesis="h", confidence="HIGH", evidence=(), missing_evidence=(), related_findings=(),
                source_paths=(), requires_runtime=False, requires_user_confirmation=False,
                status=RootCauseStatus.CONFIRMED,
            )

    def test_confirmed_with_evidence_is_accepted(self):
        rc = RootCauseCandidate(
            root_cause_id="rc1", rejection_id="r1", category=RootCauseCategory.REVIEW_ACCESS, title="t",
            hypothesis="h", confidence="HIGH", evidence=(Evidence(kind="text"),), missing_evidence=(),
            related_findings=(), source_paths=(), requires_runtime=False, requires_user_confirmation=False,
            status=RootCauseStatus.CONFIRMED,
        )
        self.assertEqual(rc.status, RootCauseStatus.CONFIRMED)

    def test_round_trip(self):
        rc = RootCauseCandidate(
            root_cause_id="rc1", rejection_id="r1", category=RootCauseCategory.UNKNOWN, title="t", hypothesis="h",
            confidence="LOW", evidence=(), missing_evidence=("x",), related_findings=("f1",), source_paths=("p",),
            requires_runtime=True, requires_user_confirmation=True, status=RootCauseStatus.UNKNOWN,
        )
        self.assertEqual(RootCauseCandidate.from_dict(rc.to_dict()).to_dict(), rc.to_dict())


class RecoveryFixPlanTests(unittest.TestCase):
    def test_non_safe_plan_requires_user_approval(self):
        with self.assertRaises(ValueError):
            RecoveryFixPlan(
                fix_id="f1", root_cause_id="rc1", finding_ids=(), safety=Safety.FORBIDDEN, title="t",
                description="d", target_paths=(), proposed_changes="none", verification_plan="v",
                reply_claim_allowed=False, requires_user_approval=False,
            )

    def test_safe_plan_may_skip_user_approval(self):
        plan = RecoveryFixPlan(
            fix_id="f1", root_cause_id="rc1", finding_ids=(), safety=Safety.SAFE, title="t", description="d",
            target_paths=(), proposed_changes="none", verification_plan="v", reply_claim_allowed=False,
            requires_user_approval=False,
        )
        self.assertEqual(plan.safety, Safety.SAFE)

    def test_round_trip(self):
        plan = RecoveryFixPlan(
            fix_id="f1", root_cause_id="rc1", finding_ids=("a",), safety=Safety.MANUAL, title="t", description="d",
            target_paths=("p",), proposed_changes="none", verification_plan="v", reply_claim_allowed=False,
            requires_user_approval=True,
        )
        self.assertEqual(RecoveryFixPlan.from_dict(plan.to_dict()).to_dict(), plan.to_dict())


class ClaimTests(unittest.TestCase):
    def test_verified_fix_claim_says_fixed(self):
        claim = Claim(claim_id="c1", subject="x", kind="fix", status=ClaimStatus.VERIFIED)
        self.assertIn("fixed", claim.statement.lower())

    def test_unverified_fix_claim_never_says_fixed_or_resolved(self):
        claim = Claim(claim_id="c1", subject="x", kind="fix", status=ClaimStatus.UNVERIFIED)
        lowered = claim.statement.lower()
        self.assertNotIn("fixed", lowered)
        self.assertNotIn("resolved", lowered)
        self.assertNotIn("corrected", lowered)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            Claim(claim_id="c1", subject="x", kind="bogus", status=ClaimStatus.VERIFIED)

    def test_round_trip(self):
        claim = Claim(claim_id="c1", subject="x", kind="dispute", status=ClaimStatus.VERIFIED, evidence_refs=("e1",))
        self.assertEqual(Claim.from_dict(claim.to_dict()).to_dict(), claim.to_dict())


class ReplyDraftTests(unittest.TestCase):
    def _draft(self, *claims):
        return ReplyDraft(
            draft_id="d1", rejection_id="r1", language="en", subject="s", body="b", claims=claims,
            response_mode="CLARIFICATION", evidence_refs=(), requires_user_review=True,
        )

    def test_forbidden_claim_blocks_ready_to_send(self):
        draft = self._draft(Claim(claim_id="c1", subject="x", kind="fix", status=ClaimStatus.FORBIDDEN_TO_CLAIM))
        self.assertFalse(draft.ready_to_send)

    def test_unverified_claim_blocks_ready_to_send(self):
        draft = self._draft(Claim(claim_id="c1", subject="x", kind="fix", status=ClaimStatus.UNVERIFIED))
        self.assertFalse(draft.ready_to_send)

    def test_all_verified_or_attested_is_ready_to_send(self):
        draft = self._draft(
            Claim(claim_id="c1", subject="x", kind="fix", status=ClaimStatus.VERIFIED),
            Claim(claim_id="c2", subject="y", kind="fix", status=ClaimStatus.USER_ATTESTED),
        )
        self.assertTrue(draft.ready_to_send)

    def test_round_trip(self):
        draft = self._draft(Claim(claim_id="c1", subject="x", kind="fix", status=ClaimStatus.VERIFIED))
        self.assertEqual(ReplyDraft.from_dict(draft.to_dict()).to_dict(), draft.to_dict())


class VerificationResultTests(unittest.TestCase):
    def test_round_trip(self):
        result = VerificationResult(
            verification_id="v1", root_cause_id="rc1", claim_status=ClaimStatus.VERIFIED, pending_reason=None,
            rechecked_rule_ids=("R1",), message="m", evidence=(Evidence(kind="recheck"),),
        )
        self.assertEqual(VerificationResult.from_dict(result.to_dict()).to_dict(), result.to_dict())


if __name__ == "__main__":
    unittest.main()
