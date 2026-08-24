import unittest
from pathlib import Path
from types import SimpleNamespace

from ios_app_store_submit.design.evaluator import run_design_review
from ios_app_store_submit.recovery.mapper import map_rejection
from ios_app_store_submit.recovery.models import (
    ClaimStatus, RootCauseCategory, RootCauseStatus, RuleMapping,
)
from ios_app_store_submit.recovery.parser import parse_rejection
from ios_app_store_submit.recovery.report import run_recovery
from ios_app_store_submit.recovery.root_cause import analyze_root_causes
from ios_app_store_submit.recovery.verifier import verify_root_cause
from ios_app_store_submit.readiness.models import Evidence
from ios_app_store_submit.review.models import Confidence


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "recovery"


class RootCauseEngineTests(unittest.TestCase):
    def test_deterministic_evidence_confirms_root_cause(self):
        result = run_recovery(
            FIXTURES / "reject_metadata_placeholder",
            FIXTURES / "reject_metadata_placeholder" / "rejection.txt",
        )
        metadata = next(item for item in result.root_causes if item.category is RootCauseCategory.METADATA)
        self.assertEqual(metadata.status, RootCauseStatus.CONFIRMED)
        self.assertEqual(metadata.confidence, Confidence.HIGH)
        self.assertTrue(metadata.evidence)
        self.assertTrue(metadata.related_findings)

    def test_crash_without_runtime_evidence_stays_unknown_and_runtime_required(self):
        result = run_recovery(
            FIXTURES / "reject_guideline_2_1_crash_unknown",
            FIXTURES / "reject_guideline_2_1_crash_unknown" / "rejection.txt",
        )
        technical = next(item for item in result.root_causes if item.category is RootCauseCategory.TECHNICAL)
        self.assertIn(technical.status, (RootCauseStatus.POSSIBLE, RootCauseStatus.UNKNOWN))
        self.assertTrue(technical.requires_runtime)
        verification = next(item for item in result.verification_results if item.root_cause_id == technical.root_cause_id)
        self.assertEqual(verification.claim_status, ClaimStatus.UNVERIFIED)
        self.assertEqual(verification.pending_reason, "requires_runtime")

    def test_review_access_case_maps_to_review_access(self):
        rejection = parse_rejection(
            "We could not sign in using the demo account credentials.", rejection_id="review-access",
        )
        mappings = map_rejection(rejection)
        mapping = next(item for item in mappings if item.category is RootCauseCategory.REVIEW_ACCESS)
        self.assertTrue(any(rule_id.startswith("REVIEW.ACCESS.") for rule_id in mapping.mapped_rule_ids))

    def test_localization_case_maps_and_can_be_confirmed_by_design_engine(self):
        project = FIXTURES / "reject_localization_missing_key"
        rejection = parse_rejection((project / "rejection.txt").read_text(), rejection_id="localization")
        mappings = map_rejection(rejection)
        self.assertTrue(any(item.category is RootCauseCategory.LOCALIZATION for item in mappings))

        result = run_recovery(project, project / "rejection.txt", design_result=run_design_review(project))
        localization = next(item for item in result.root_causes if item.category is RootCauseCategory.LOCALIZATION)
        self.assertEqual(localization.status, RootCauseStatus.CONFIRMED)
        self.assertTrue(localization.related_findings)

    def test_contradictory_local_check_prevents_confirmed_root_cause(self):
        project = FIXTURES / "reject_dispute_with_evidence"
        result = run_recovery(project, project / "rejection.txt")
        metadata = next(item for item in result.root_causes if item.category is RootCauseCategory.METADATA)
        self.assertEqual(metadata.status, RootCauseStatus.CONTRADICTED)
        self.assertNotEqual(metadata.status, RootCauseStatus.CONFIRMED)

    def test_user_confirmation_is_an_explicit_gate(self):
        rejection = parse_rejection("A policy concern was reported.", rejection_id="policy")
        mapping = RuleMapping(
            mapping_id="mapping:policy:legal", rejection_id="policy", apple_guideline=None,
            mapped_rule_ids=(), category=RootCauseCategory.LEGAL_POLICY,
            confidence=Confidence.MEDIUM, evidence=(Evidence(kind="text", observed="policy"),),
            mapping_reason="keyword signal",
        )
        root_cause = analyze_root_causes(rejection, [mapping])[0]
        self.assertTrue(root_cause.requires_user_confirmation)
        self.assertEqual(root_cause.status, RootCauseStatus.UNKNOWN)

        without_attestation = verify_root_cause(root_cause)
        self.assertEqual(without_attestation.claim_status, ClaimStatus.FORBIDDEN_TO_CLAIM)
        with_attestation = verify_root_cause(
            root_cause, attestations={"LEGAL_POLICY": {"attested": True, "note": "Counsel confirmed."}},
        )
        self.assertEqual(with_attestation.claim_status, ClaimStatus.USER_ATTESTED)
        self.assertTrue(with_attestation.evidence)


if __name__ == "__main__":
    unittest.main()
