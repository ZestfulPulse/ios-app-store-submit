"""Fixture-backed coverage for the Phase 2 Safe Auto-Fix loop.

test_readiness_fixes.py covers the in-memory foundation; this module exercises
the eight Phase 2F fixtures end to end (CLI + library) and the checklist items
that foundation module does not reach: stale-plan detection, rollback, the
MANUAL/FORBIDDEN safety boundary at the fixture level, external-mutation and
delete/rename guards, and JSON evidence round-tripping.
"""

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.readiness.fixes.models import FixOperation, FixPlan, FixSafety
from ios_app_store_submit.readiness.fixes.planner import plan_fixes
from ios_app_store_submit.readiness.fixes.safe_fixes import plan_empty_directory
from ios_app_store_submit.readiness.fixes.verifier import apply_plans
from ios_app_store_submit.readiness.inspector import ProjectInspector
from ios_app_store_submit.readiness.models import Evidence, Finding, Status
from ios_app_store_submit.readiness.report import build_report

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "readiness"


def copied_fixture(name: str, directory: str) -> Path:
    target = Path(directory) / "project"
    shutil.copytree(FIXTURES / name, target, ignore=shutil.ignore_patterns(".asc"))
    return target


def all_hashes(root: Path) -> dict[Path, str]:
    return {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


class FixtureExistenceTests(unittest.TestCase):
    def test_all_phase2_fixtures_exist(self):
        expected = {
            "safe_missing_scaffold", "safe_format_normalization", "stale_plan", "failed_verify",
            "forbidden_bundle_id", "forbidden_signing", "forbidden_privacy", "user_authored_content_protected",
        }
        for name in expected:
            self.assertTrue((FIXTURES / name).is_dir(), f"missing fixture: {name}")


class SafeMissingScaffoldTests(unittest.TestCase):
    def test_missing_scaffold_apply_creates_only_target_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("safe_missing_scaffold", directory)
            self.assertFalse((target / "ios/Runner/en.lproj").exists())
            before = all_hashes(target)
            plan = plan_empty_directory(
                ProjectInspector(target), "ios/Runner/en.lproj",
                finding_id="metadata.localized_app_name",
                title="Create missing localization scaffold",
                reason="ios/Runner/en.lproj is absent locally; creating it is non-destructive scaffolding.",
                verification_rule="scaffold:ios/Runner/en.lproj",
                rule_id="LOCALIZED_APP_NAME",
            )
            self.assertEqual(plan.operation, FixOperation.CREATE)
            result = apply_plans(target, [plan])[0]
            after = all_hashes(target)
            self.assertEqual(result.status, "VERIFIED")
            self.assertEqual(result.rollback, "NOT_NEEDED")
            self.assertTrue((target / "ios/Runner/en.lproj").is_dir())
            self.assertEqual(before, {p: h for p, h in after.items() if p in before})


class SafeFormatNormalizationTests(unittest.TestCase):
    def test_plan_fixes_cli_is_zero_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("safe_format_normalization", directory)
            before = all_hashes(target)
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(target), "--plan-fixes"],
                cwd=ROOT, capture_output=True, text=True,
            )
            after = all_hashes(target)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(before, after)
            self.assertIn("safe.normalize_pubspec_version", result.stdout)
            self.assertIn("safe.normalize_display_name", result.stdout)

    def test_apply_safe_fixes_cli_changes_only_intended_files_and_reruns_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("safe_format_normalization", directory)
            before = all_hashes(target)
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(target), "--apply-safe-fixes"],
                cwd=ROOT, capture_output=True, text=True,
            )
            after = all_hashes(target)
            self.assertEqual(result.returncode, 0, result.stdout)
            changed = {path for path in before if before[path] != after.get(path)}
            self.assertEqual(changed, {Path("pubspec.yaml"), Path("ios/Runner/Info.plist")})
            report = build_report(target)
            version = next(f for f in report.findings if f.finding_id == "technical.pubspec_version")
            display = next(f for f in report.findings if f.finding_id == "metadata.display_name")
            self.assertEqual(version.status, Status.PASS)
            self.assertEqual(display.status, Status.PASS)


class StalePlanTests(unittest.TestCase):
    def test_drift_after_planning_causes_stale_plan_and_zero_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("stale_plan", directory)
            plans = plan_fixes(target)
            plan = next(p for p in plans if p.target_path == "pubspec.yaml")
            # Simulate an external actor changing the file after the plan was built.
            pubspec = target / "pubspec.yaml"
            pubspec.write_text(pubspec.read_text().replace("version: '1.2.3+4'", "version: '9.9.9+9'"))
            drifted = pubspec.read_bytes()
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "STALE_PLAN")
            self.assertEqual(result.rollback, "NOT_APPLICABLE")
            self.assertFalse(plan.applied)
            self.assertEqual(pubspec.read_bytes(), drifted)


class FailedVerifyRollbackTests(unittest.TestCase):
    def test_failed_verify_fixture_restores_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("failed_verify", directory)
            info = target / "ios/Runner/Info.plist"
            before_bytes = info.read_bytes()
            before_hash = hashlib.sha256(before_bytes).hexdigest()
            plan = FixPlan(
                fix_id="safe.normalize_display_name", finding_id="metadata.display_name",
                safety=FixSafety.SAFE, title="Normalize local display-name formatting",
                target_path="ios/Runner/Info.plist",
                before="<key>CFBundleDisplayName</key><string> ${UNRESOLVED} </string>",
                proposed_after="<key>CFBundleDisplayName</key><string>${UNRESOLVED}</string>",
                reason="test", verification_rule="metadata.display_name",
                operation=FixOperation.UPDATE_FORMAT, rule_id="DISPLAY_NAME",
            )
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "FAILED_VERIFY")
            self.assertEqual(result.rollback, "ROLLED_BACK")
            self.assertEqual(result.before_hash, before_hash)
            self.assertIsNotNone(result.after_hash)
            self.assertNotEqual(result.before_hash, result.after_hash)
            self.assertFalse(plan.applied)
            self.assertFalse(plan.verified)
            self.assertEqual(info.read_bytes(), before_bytes)


class ForbiddenFixtureTests(unittest.TestCase):
    def test_forbidden_bundle_id_fixture_never_auto_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("forbidden_bundle_id", directory)
            pbx = target / "ios/Runner.xcodeproj/project.pbxproj"
            before = pbx.read_bytes()
            finding = Finding("technical.bundle_id", "TECHNICAL", "BUNDLE_ID", "Bundle ID", Status.PASS,
                              "com.example.readiness", (Evidence("xcode_setting", path="ios/Runner.xcodeproj/project.pbxproj"),))
            plan = FixPlan("forbidden.bundle_id", finding.finding_id, FixSafety.FORBIDDEN, "attempted bundle id change",
                          "ios/Runner.xcodeproj/project.pbxproj", "com.example.readiness", "com.example.changed",
                          "forbidden", finding.finding_id)
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(pbx.read_bytes(), before)

    def test_forbidden_signing_fixture_never_auto_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("forbidden_signing", directory)
            pbx = target / "ios/Runner.xcodeproj/project.pbxproj"
            before = pbx.read_bytes()
            plan = FixPlan("forbidden.signing", "technical.signing", FixSafety.FORBIDDEN, "attempted signing change",
                          "ios/Runner.xcodeproj/project.pbxproj", "ABCDE12345", "ZZZZZ99999",
                          "forbidden", "technical.signing")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(pbx.read_bytes(), before)

    def test_forbidden_privacy_fixture_never_auto_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("forbidden_privacy", directory)
            before = all_hashes(target)
            plan = FixPlan("forbidden.app_privacy", "metadata.app_privacy", FixSafety.FORBIDDEN,
                          "attempted App Privacy declaration change", "external state", "unset", "declared",
                          "forbidden", "metadata.app_privacy")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(all_hashes(target), before)


class UserAuthoredContentProtectionTests(unittest.TestCase):
    def test_mismatched_plan_against_user_authored_file_does_not_mutate_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("user_authored_content_protected", directory)
            main_dart = target / "lib/main.dart"
            before = main_dart.read_bytes()
            self.assertIn(b"Hand-authored", before)
            plan = FixPlan(
                fix_id="unsafe.rewrite_main", finding_id="metadata.display_name", safety=FixSafety.SAFE,
                title="unsafe", target_path="lib/main.dart",
                before="void main() {}", proposed_after="void main() { runApp(MyApp()); }",
                reason="not a real SAFE target", verification_rule="metadata.display_name",
            )
            result = apply_plans(target, [plan])[0]
            self.assertIn(result.status, ("STALE_PLAN", "FAILED_VERIFY"))
            self.assertFalse(plan.applied)
            self.assertEqual(main_dart.read_bytes(), before)


class ManualNeverAutoAppliesTests(unittest.TestCase):
    def test_manual_safety_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("safe_format_normalization", directory)
            before = (target / "pubspec.yaml").read_bytes()
            plan = FixPlan("manual.review", "metadata.support_url", FixSafety.MANUAL, "manual",
                          "pubspec.yaml", "before", "after", "manual review required",
                          "metadata.support_url")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual((target / "pubspec.yaml").read_bytes(), before)


class NoDeleteOrRenameOperationTests(unittest.TestCase):
    def test_fix_operation_enum_has_no_delete_or_rename(self):
        values = {member.value for member in FixOperation}
        self.assertEqual(values, {"CREATE", "UPDATE_FORMAT", "NORMALIZE_VALUE"})
        self.assertNotIn("DELETE", values)
        self.assertNotIn("RENAME", values)

    def test_verifier_source_contains_no_delete_or_rename_calls(self):
        source = (ROOT / "ios_app_store_submit/readiness/fixes/verifier.py").read_text()
        for forbidden in ("os.remove", "shutil.rmtree", ".rename(", ".unlink(", "os.replace"):
            self.assertNotIn(forbidden, source)


class NoExternalMutationTests(unittest.TestCase):
    def test_fix_modules_never_shell_out_or_touch_the_network(self):
        for name in ("verifier.py", "planner.py", "safe_fixes.py"):
            source = (ROOT / "ios_app_store_submit/readiness/fixes" / name).read_text()
            for forbidden in ("subprocess", "urllib", "requests", "socket", "asc "):
                self.assertNotIn(forbidden, source, f"{name} references {forbidden!r}")


class FixEvidenceJsonRoundTripTests(unittest.TestCase):
    def test_apply_safe_fixes_json_report_round_trips_fix_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("safe_format_normalization", directory)
            result = subprocess.run(
                [sys.executable, "scripts/readiness_check.py", str(target), "--apply-safe-fixes", "--json"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            import json
            payload = json.loads(result.stdout)
            for key in ("fix_plans", "applied_fixes", "verification_results", "rollback_results"):
                self.assertIn(key, payload)
            self.assertTrue(payload["applied_fixes"])
            for entry in payload["fix_plans"]:
                restored = FixPlan.from_dict(entry)
                self.assertEqual(restored.to_dict(), entry)
            for entry in payload["applied_fixes"]:
                self.assertIn("before_hash", entry)
                self.assertIn("after_hash", entry)
                self.assertIn("diff", entry)
                self.assertIn("verification_rule", entry)
                self.assertIn("status", entry)
            verified = {item["fix_id"]: item for item in payload["verification_results"]}
            self.assertTrue(all(item["result"] == "VERIFIED" for item in verified.values()))


if __name__ == "__main__":
    unittest.main()
