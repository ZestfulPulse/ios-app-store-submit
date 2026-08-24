import json
import subprocess
import sys
import unittest
from pathlib import Path

from ios_app_store_submit.design.evaluator import run_design_review
from ios_app_store_submit.design.report import human_summary, load_design_evidence

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


class HumanSummaryTests(unittest.TestCase):
    def test_summary_contains_required_sections_and_disclaimer(self):
        result = run_design_review(FIXTURES / "design_valid_basic")
        text = human_summary(result)
        self.assertIn("=== HIG / DESIGN REVIEW ===", text)
        self.assertIn("DESIGN_GATE:", text)
        self.assertIn("Design review is a risk assessment, not an Apple approval guarantee.", text)
        for area in ("ACCESSIBILITY", "LAYOUT", "LOCALIZATION", "INTERACTION"):
            self.assertIn(area, text)


class DesignEvidenceLoaderTests(unittest.TestCase):
    def test_load_design_evidence_reads_json_object(self, ):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps({"rendered_sizes": {}}))
            data = load_design_evidence(path)
        self.assertEqual(data, {"rendered_sizes": {}})

    def test_load_design_evidence_rejects_non_object(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text("[1, 2, 3]")
            with self.assertRaises(ValueError):
                load_design_evidence(path)


class CliIntegrationTests(unittest.TestCase):
    def test_design_json_extends_readiness_report(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "design_valid_basic"),
             "--design", "--json"],
            cwd=ROOT, capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        for key in ("design_review", "design_ruleset", "design_findings", "design_summary", "ready", "findings"):
            self.assertIn(key, payload)

    def test_design_output_precedes_existing_readiness_summary(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "design_valid_basic"), "--design"],
            cwd=ROOT, capture_output=True, text=True,
        )
        design_at = result.stdout.index("=== HIG / DESIGN REVIEW ===")
        readiness_at = result.stdout.index("=== IOS APP STORE READINESS SUMMARY ===")
        self.assertLess(design_at, readiness_at)

    def test_blocked_design_gate_causes_nonzero_exit(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "design_small_explicit_control"),
             "--design"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)

    def test_valid_basic_has_no_false_blocked(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "design_valid_basic"), "--design"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("DETERMINISTIC FINDINGS  0", result.stdout)

    def test_design_privacy_and_pre_review_can_all_run_together(self):
        result = subprocess.run(
            [sys.executable, "scripts/readiness_check.py", str(FIXTURES / "design_valid_basic"),
             "--design", "--privacy", "--pre-review"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertIn("=== HIG / DESIGN REVIEW ===", result.stdout)
        self.assertIn("=== APP PRIVACY INTELLIGENCE ===", result.stdout)
        self.assertIn("=== APP STORE PRE-REVIEW ===", result.stdout)
        self.assertIn("=== IOS APP STORE READINESS SUMMARY ===", result.stdout)

    def test_no_network_no_simulator_no_device_launch_by_default(self):
        from unittest import mock

        with mock.patch("socket.socket", side_effect=AssertionError("network access attempted")):
            result = run_design_review(FIXTURES / "design_valid_basic")
        self.assertTrue(result.findings)


class RegressionTests(unittest.TestCase):
    def test_existing_submission_flow_and_scripts_are_untouched(self):
        skill = (ROOT / "SKILL.md").read_text()
        for text in ("asc xcode archive", "asc publish appstore", "asc review submit", "WAITING_FOR_REVIEW"):
            self.assertIn(text, skill)
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", "scripts/gen_app_icons.py", "scripts/setup_build_keychain.sh"],
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0)

    def test_privacy_boundaries_preserved(self):
        # Running --design must not alter privacy's own zero-mutation, read-only behavior.
        package_root = ROOT / "ios_app_store_submit" / "privacy"
        for path in package_root.glob("*.py"):
            text = path.read_text()
            self.assertNotIn("subprocess", text, path)
            self.assertNotIn(".write_text(", text, path)


class AuthoredAscFixtureRegressionTests(unittest.TestCase):
    """Guards item P.33: authored fixture input under fixtures/**/.asc/ must
    stay tracked in git even though the repository .gitignore excludes .asc/
    wholesale (that rule exists to keep *generated* readiness-report.json
    output out of version control, not to swallow authored fixture input).

    This does not change .gitignore; it verifies, from the git index itself,
    that every .asc file physically present in a fixture directory whose
    filename does not look like the generated report is actually tracked --
    i.e. that a plain ``git add fixtures`` (which respects .gitignore) would
    not silently drop it, the way it would have to be force-added originally.
    """

    GENERATED_ASC_FILENAMES = {"readiness-report.json"}

    def test_authored_asc_fixture_files_are_tracked(self):
        asc_files = sorted(FIXTURES.glob("*/.asc/*"))
        authored = [path for path in asc_files if path.name not in self.GENERATED_ASC_FILENAMES]
        self.assertTrue(authored, "expected at least one authored fixture file under fixtures/**/.asc/")
        for path in authored:
            relative = path.relative_to(ROOT).as_posix()
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", relative], cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(
                result.returncode, 0,
                f"{relative} is authored fixture input under a gitignored .asc/ directory but is not "
                "tracked by git -- it will silently disappear for anyone who clones the repo. Force-add it "
                "explicitly (git add -f) rather than relying on a directory-wide `git add`.",
            )


if __name__ == "__main__":
    unittest.main()
