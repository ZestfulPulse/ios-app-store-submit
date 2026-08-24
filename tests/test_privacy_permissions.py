import unittest
from pathlib import Path

from ios_app_store_submit.privacy.inspector import inspect_permissions
from ios_app_store_submit.privacy.models import TriState
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class PermissionInspectionTests(unittest.TestCase):
    def test_permission_declaration_implies_access_only(self):
        inspector = ProjectInspector(FIXTURES / "privacy_permission_only")
        evidence = inspect_permissions(inspector)
        self.assertEqual(len(evidence), 1)
        item = evidence[0]
        self.assertEqual(item.data_type_candidate, "LOCATION")
        self.assertEqual(item.access, TriState.YES)

    def test_permission_declaration_does_not_imply_collection(self):
        inspector = ProjectInspector(FIXTURES / "privacy_permission_only")
        item = inspect_permissions(inspector)[0]
        self.assertEqual(item.collection, TriState.UNKNOWN)
        for claim in ("collects", "transmits", "sends data"):
            self.assertNotIn(claim, item.notes.lower())

    def test_permission_declaration_does_not_imply_tracking(self):
        inspector = ProjectInspector(FIXTURES / "privacy_permission_only")
        item = inspect_permissions(inspector)[0]
        self.assertEqual(item.tracking, TriState.UNKNOWN)

    def test_permission_declaration_requires_user_confirmation(self):
        inspector = ProjectInspector(FIXTURES / "privacy_permission_only")
        item = inspect_permissions(inspector)[0]
        self.assertTrue(item.requires_user_confirmation)

    def test_no_permission_no_evidence(self):
        inspector = ProjectInspector(FIXTURES / "privacy_no_signals")
        self.assertEqual(inspect_permissions(inspector), [])


if __name__ == "__main__":
    unittest.main()
