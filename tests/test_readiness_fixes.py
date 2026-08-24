import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.readiness.fixes.models import FixPlan, FixSafety
from ios_app_store_submit.readiness.fixes.planner import plan_fixes, plan_for_finding
from ios_app_store_submit.readiness.fixes.safe_fixes import plan_empty_directory
from ios_app_store_submit.readiness.fixes.verifier import apply_plans, verify_plan
from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.models import Evidence, Finding, Status
from ios_app_store_submit.readiness.report import build_report


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "readiness" / "valid_flutter"


def copied_fixture(directory: str) -> Path:
    target = Path(directory) / "project"
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns(".asc"))
    return target


class FixFoundationTests(unittest.TestCase):
    def test_safe_fix_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            pubspec = target / "pubspec.yaml"
            pubspec.write_text(pubspec.read_text().replace("version: 1.2.3+4", "version: '1.2.3+4'"))
            info = target / "ios/Runner/Info.plist"
            info.write_text(info.read_text().replace("<string>Readiness Fixture</string>", "<string> Readiness Fixture </string>", 1))
            plans = plan_fixes(target)
        safe_plans = [plan for plan in plans if plan.safety is FixSafety.SAFE]
        self.assertEqual({plan.target_path for plan in safe_plans}, {"pubspec.yaml", "ios/Runner/Info.plist"})
        self.assertTrue(all(plan.safety is FixSafety.SAFE for plan in safe_plans))

    def test_dry_run_causes_zero_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            before = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(target), "--plan-fixes"],
                cwd=ROOT, capture_output=True, text=True,
            )
            after = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
            self.assertEqual(result.returncode, 0)
            self.assertEqual(before, after)
            self.assertFalse((target / ".asc").exists())

    def test_safe_fix_apply_changes_only_intended_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            info = target / "ios/Runner/Info.plist"
            info.write_text(info.read_text().replace("<string>Readiness Fixture</string>", "<string> Readiness Fixture </string>", 1))
            pbx = target / "ios/Runner.xcodeproj/project.pbxproj"
            pbx_before = pbx.read_bytes()
            plans = plan_fixes(target)
            results = apply_plans(target, [plan for plan in plans if plan.target_path == "ios/Runner/Info.plist"])
            self.assertEqual([item.status for item in results], ["VERIFIED"])
            self.assertNotEqual(info.read_text(), "")
            self.assertEqual(pbx.read_bytes(), pbx_before)
            self.assertIn("<string>Readiness Fixture</string>", info.read_text())

    def test_verification_is_required_after_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            info = target / "ios/Runner/Info.plist"
            info.write_text(info.read_text().replace("<string>Readiness Fixture</string>", "<string> Readiness Fixture </string>", 1))
            plan = next(item for item in plan_fixes(target) if item.target_path == "ios/Runner/Info.plist")
            results = apply_plans(target, [plan])
            self.assertTrue(plan.applied)
            self.assertTrue(plan.verified)
            self.assertTrue(verify_plan(plan, target))
            self.assertEqual(results[0].status, "VERIFIED")
            self.assertTrue(results[0].diff)

    def test_failed_verification_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            info = target / "ios/Runner/Info.plist"
            before = info.read_text()
            old = "<key>CFBundleDisplayName</key><string>Readiness Fixture</string>"
            plan = FixPlan("test.bad", "metadata.display_name", FixSafety.SAFE, "bad", "ios/Runner/Info.plist",
                           old, "<key>CFBundleDisplayName</key><string>${UNRESOLVED}</string>", "test", "metadata.display_name")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "FAILED_VERIFY")
            self.assertFalse(plan.applied)
            self.assertFalse(plan.verified)
            self.assertEqual(info.read_text(), before)

    def test_approval_required_cannot_auto_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            before = (target / "pubspec.yaml").read_bytes()
            plan = FixPlan("approval", "metadata.support_url", FixSafety.APPROVAL_REQUIRED, "approval", "pubspec.yaml", "before", "after", "approval", "metadata.support_url")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual((target / "pubspec.yaml").read_bytes(), before)

    def test_forbidden_cannot_auto_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            before = (target / "ios/Runner.xcodeproj/project.pbxproj").read_bytes()
            plan = FixPlan("forbidden", "technical.bundle_id", FixSafety.FORBIDDEN, "forbidden", "ios/Runner.xcodeproj/project.pbxproj", "before", "after", "forbidden", "technical.bundle_id")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual((target / "ios/Runner.xcodeproj/project.pbxproj").read_bytes(), before)

    def test_bundle_id_cannot_auto_change(self):
        finding = Finding("technical.bundle_id", "TECHNICAL", "BUNDLE_ID", "Bundle ID", Status.BLOCKED, "missing", (Evidence("xcode_setting", path="ios/Runner.xcodeproj/project.pbxproj"),), "ios/Runner.xcodeproj/project.pbxproj")
        plan = plan_for_finding(finding)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.safety, FixSafety.FORBIDDEN)

    def test_signing_cannot_auto_change(self):
        finding = Finding("technical.signing", "TECHNICAL", "SIGNING", "Signing", Status.RISK, "signing", (Evidence("inspection"),))
        plan = plan_for_finding(finding)
        self.assertEqual(plan.safety, FixSafety.FORBIDDEN)

    def test_app_privacy_cannot_auto_change(self):
        finding = Finding("metadata.app_privacy", "METADATA", "APP_PRIVACY", "App Privacy", Status.UNKNOWN, "external", (Evidence("inspection"),))
        plan = plan_for_finding(finding)
        self.assertEqual(plan.safety, FixSafety.FORBIDDEN)

        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            info = target / "ios/Runner/Info.plist"
            before = info.read_bytes()
            forced_safe = FixPlan("unsafe", "metadata.app_privacy", FixSafety.SAFE, "unsafe", "ios/Runner/Info.plist", "before", "after", "unsafe", "metadata.app_privacy")
            self.assertEqual(apply_plans(target, [forced_safe])[0].status, "SKIPPED")
            self.assertEqual(info.read_bytes(), before)

    def test_empty_directory_scaffold_is_explicit_and_verifiable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture(directory)
            plan = plan_empty_directory(ProjectInspector(target), "local_scaffold", finding_id="metadata.localizations",
                                        title="Create local scaffold", reason="Explicit test scaffold", verification_rule="scaffold:local_scaffold")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "VERIFIED")
            self.assertTrue((target / "local_scaffold").is_dir())

    def test_phase1_report_and_submission_workflow_remain_intact(self):
        report = build_report(FIXTURE)
        self.assertEqual(report.counts["BLOCKED"], 0)
        skill = (ROOT / "SKILL.md").read_text()
        for text in ("asc xcode archive", "asc publish appstore", "asc review submit", "WAITING_FOR_REVIEW"):
            self.assertIn(text, skill)
