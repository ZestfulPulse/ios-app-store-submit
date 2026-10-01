import unittest
from pathlib import Path

from ios_app_store_submit.readiness.gates.metadata import inspect_metadata
from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.models import Status


FIXTURES = Path(__file__).parents[1] / "fixtures" / "readiness"


class MetadataGateTests(unittest.TestCase):
    def test_valid_local_candidates_are_found(self):
        result = inspect_metadata(ProjectInspector(FIXTURES / "valid_flutter"))
        by_rule = {item.rule_id: item for item in result.findings}
        self.assertEqual(by_rule["DISPLAY_NAME"].status, Status.PASS)
        self.assertEqual(by_rule["PRIVACY_POLICY"].status, Status.PASS)
        self.assertEqual(by_rule["SUPPORT_URL"].status, Status.PASS)
        self.assertEqual(by_rule["LOCALIZED_APP_NAME"].status, Status.PASS)

    def test_missing_privacy_policy_does_not_invent_pass(self):
        result = inspect_metadata(ProjectInspector(FIXTURES / "missing_privacy_policy"))
        privacy = next(item for item in result.findings if item.rule_id == "PRIVACY_POLICY")
        self.assertEqual(privacy.status, Status.UNKNOWN)

    def test_unresolved_build_variable_display_name_is_not_pass(self):
        # "$(PRODUCT_NAME)" is the default CFBundleDisplayName; it is an unresolved
        # Xcode build variable, not a finalized name. Consistent with the version
        # check, which treats "$(" as unresolved (technical.py).
        result = inspect_metadata(ProjectInspector(FIXTURES / "metadata_display_name_build_var"))
        display = next(item for item in result.findings if item.rule_id == "DISPLAY_NAME")
        self.assertEqual(display.status, Status.UNKNOWN)
