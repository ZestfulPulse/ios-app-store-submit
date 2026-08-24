import unittest
from pathlib import Path

from ios_app_store_submit.privacy.inspector import inspect_network_signals
from ios_app_store_submit.privacy.models import TriState
from ios_app_store_submit.privacy.sdk_catalog import inspect_dependencies
from ios_app_store_submit.readiness.inspector import ProjectInspector

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class SdkCatalogTests(unittest.TestCase):
    def test_known_sdk_presence_is_detected(self):
        inspector = ProjectInspector(FIXTURES / "privacy_sdk_analytics_present")
        evidence = inspect_dependencies(inspector)
        self.assertEqual([e.observed for e in evidence], ["firebase_analytics"])

    def test_sdk_presence_does_not_imply_collection(self):
        inspector = ProjectInspector(FIXTURES / "privacy_sdk_analytics_present")
        item = inspect_dependencies(inspector)[0]
        self.assertEqual(item.collection, TriState.UNKNOWN)
        self.assertEqual(item.transmission, TriState.UNKNOWN)
        self.assertTrue(item.requires_user_confirmation)

    def test_unknown_package_produces_no_sdk_evidence(self):
        inspector = ProjectInspector(FIXTURES / "privacy_generic_http_only")
        self.assertEqual(inspect_dependencies(inspector), [])


class NetworkSignalTests(unittest.TestCase):
    def test_generic_http_dependency_does_not_imply_transmission(self):
        inspector = ProjectInspector(FIXTURES / "privacy_generic_http_only")
        evidence = inspect_network_signals(inspector)
        self.assertEqual(len(evidence), 1)
        item = evidence[0]
        self.assertEqual(item.kind, "network_http_client")
        self.assertEqual(item.transmission, TriState.UNKNOWN)
        self.assertEqual(item.confidence.value, "LOW")

    def test_identifiable_data_path_is_possible_not_proven(self):
        inspector = ProjectInspector(FIXTURES / "privacy_location_network_possible")
        evidence = inspect_network_signals(inspector)
        path_evidence = [e for e in evidence if e.kind == "network_identifiable_data_path"]
        self.assertEqual(len(path_evidence), 1)
        self.assertEqual(path_evidence[0].transmission, TriState.UNKNOWN)
        self.assertEqual(path_evidence[0].confidence.value, "MEDIUM")

    def test_no_signals_project_has_no_network_evidence(self):
        inspector = ProjectInspector(FIXTURES / "privacy_no_signals")
        self.assertEqual(inspect_network_signals(inspector), [])


if __name__ == "__main__":
    unittest.main()
