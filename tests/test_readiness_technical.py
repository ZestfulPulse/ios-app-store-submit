import shutil
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.readiness.gates.technical import inspect_technical
from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.models import Status


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class TechnicalGateTests(unittest.TestCase):
    def test_valid_flutter_has_no_blocked_findings(self):
        result = inspect_technical(ProjectInspector(FIXTURES / "valid_flutter"))
        self.assertNotIn(Status.BLOCKED, {item.status for item in result.findings})

    def test_missing_pubspec_version_is_blocked(self):
        result = inspect_technical(ProjectInspector(FIXTURES / "missing_version"))
        self.assertEqual(result.status, Status.BLOCKED)
        self.assertTrue(any(item.rule_id == "PUBSPEC_VERSION" and item.status is Status.BLOCKED for item in result.findings))

    def test_missing_bundle_id_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "project"
            shutil.copytree(FIXTURES / "valid_flutter", target)
            pbx = target / "ios/Runner.xcodeproj/project.pbxproj"
            pbx.write_text(pbx.read_text().replace("PRODUCT_BUNDLE_IDENTIFIER = com.example.readiness;", "PRODUCT_BUNDLE_IDENTIFIER = ;"))
            result = inspect_technical(ProjectInspector(target))
        self.assertTrue(any(item.rule_id == "BUNDLE_ID" and item.status is Status.BLOCKED for item in result.findings))

    def test_unparseable_value_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "project"
            shutil.copytree(FIXTURES / "valid_flutter", target)
            pbx = target / "ios/Runner.xcodeproj/project.pbxproj"
            pbx.write_text(pbx.read_text().replace("PRODUCT_BUNDLE_IDENTIFIER = com.example.readiness;", "PRODUCT_BUNDLE_IDENTIFIER = $(PRODUCT_BUNDLE_IDENTIFIER);"))
            result = inspect_technical(ProjectInspector(target))
        self.assertTrue(any(item.rule_id == "BUNDLE_ID" and item.status is Status.UNKNOWN for item in result.findings))
