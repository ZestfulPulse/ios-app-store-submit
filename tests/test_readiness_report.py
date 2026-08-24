import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.readiness.models import Evidence, Finding, GateResult, ReadinessReport, Status
from ios_app_store_submit.readiness.report import build_report, report_from_json, write_json


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class ReportTests(unittest.TestCase):
    def test_blocked_means_ready_no(self):
        report = build_report(FIXTURES / "missing_version")
        self.assertEqual(report.ready, "NO")

    def test_unknown_only_means_conditional(self):
        finding = Finding("m.unknown", "METADATA", "UNKNOWN", "unknown", Status.UNKNOWN, "unknown", (Evidence("inspection"),))
        report = ReadinessReport("demo", (GateResult("METADATA", (finding,)),))
        self.assertEqual(report.ready, "CONDITIONAL")

    def test_strict_unknown_fails(self):
        finding = Finding("m.unknown", "METADATA", "UNKNOWN", "unknown", Status.UNKNOWN, "unknown", (Evidence("inspection"),))
        report = ReadinessReport("demo", (GateResult("METADATA", (finding,)),), strict=True)
        self.assertEqual(report.ready, "NO")

    def test_json_round_trip(self):
        report = build_report(FIXTURES / "valid_flutter")
        with tempfile.TemporaryDirectory() as directory:
            path = write_json(report, Path(directory) / "report.json")
            loaded = report_from_json(path)
        self.assertEqual(loaded.to_dict(), report.to_dict())

    def test_stable_report_ordering(self):
        a = Finding("z", "METADATA", "Z", "z", Status.PASS, "z")
        b = Finding("a", "TECHNICAL", "A", "a", Status.PASS, "a")
        report = ReadinessReport("demo", (GateResult("METADATA", (a,)), GateResult("TECHNICAL", (b,))))
        self.assertEqual([item["finding_id"] for item in report.to_dict()["findings"]], ["a", "z"])

    def test_existing_submission_flow_and_scripts_are_untouched(self):
        skill = (ROOT / "SKILL.md").read_text()
        for text in ("asc xcode archive", "asc publish appstore", "asc review submit", "WAITING_FOR_REVIEW"):
            self.assertIn(text, skill)
        result = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "scripts/gen_app_icons.py", "scripts/setup_build_keychain.sh"], cwd=ROOT)
        self.assertEqual(result.returncode, 0)

    def test_cli_json_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "readiness.json"
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "valid_flutter"), "--json", "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["project"], str((FIXTURES / "valid_flutter").resolve()))
            self.assertTrue(output.exists())
