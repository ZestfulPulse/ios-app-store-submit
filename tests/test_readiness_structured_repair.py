"""Coverage for the two remaining Phase 2A SAFE-fix categories:

- malformed structured-file repair (JSON / YAML / plist)
- non-fabricating placeholder/scaffold creation

Each test is keyed to the fixture letter from the Phase 2A closure mission
(A-I) in its docstring/name; J-N are covered by the fixtures and tests added
in the previous Phase 2 pass (safe_format_normalization, stale_plan,
failed_verify, forbidden_*, user_authored_content_protected) and are not
duplicated here. O (full existing suite still PASS) is verified by running
the whole discovery run, not from inside this module.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.readiness.fixes.models import FixOperation, FixSafety
from ios_app_store_submit.readiness.fixes.planner import plan_fixes
from ios_app_store_submit.readiness.fixes.verifier import apply_plans
from ios_app_store_submit.readiness.models import Status
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


class MalformedJsonRecoverableTests(unittest.TestCase):
    """A. malformed JSON with recoverable syntax."""

    def test_trailing_comma_json_gets_a_safe_plan_and_applies_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("malformed_json_recoverable", directory)
            config = target / "config/app_config.json"
            with self.assertRaises(json.JSONDecodeError):
                json.loads(config.read_text())

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.target_path == "config/app_config.json")
            self.assertEqual(plan.safety, FixSafety.SAFE)
            self.assertEqual(plan.operation, FixOperation.UPDATE_FORMAT)

            before_hash = hashlib.sha256(config.read_bytes()).hexdigest()
            other_before = all_hashes(target)
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "VERIFIED")
            self.assertEqual(result.rollback, "NOT_NEEDED")
            self.assertEqual(result.before_hash, before_hash)
            self.assertNotEqual(result.after_hash, before_hash)
            self.assertTrue(result.diff)

            after_data = json.loads(config.read_text())
            self.assertEqual(after_data, {"name": "readiness_fixture", "flags": ["a", "b"]})
            other_after = all_hashes(target)
            self.assertEqual(
                {k: v for k, v in other_before.items() if k != Path("config/app_config.json")},
                {k: v for k, v in other_after.items() if k != Path("config/app_config.json")},
            )


class MalformedJsonAmbiguousTests(unittest.TestCase):
    """B. malformed JSON whose semantics are ambiguous -> MANUAL/no mutation."""

    def test_truncated_json_is_classified_manual_and_never_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("malformed_json_ambiguous", directory)
            config = target / "config/app_config.json"
            before = config.read_bytes()

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.target_path == "config/app_config.json")
            self.assertEqual(plan.safety, FixSafety.MANUAL)
            self.assertIsNone(plan.proposed_after)

            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(config.read_bytes(), before)


class MalformedYamlSafeRepairTests(unittest.TestCase):
    """C. malformed YAML safe conservative repair."""

    def test_mismatched_quotes_around_valid_version_are_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("malformed_yaml_safe_repair", directory)
            pubspec = target / "pubspec.yaml"

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.fix_id == "safe.repair_yaml_pubspec_version_quotes")
            self.assertEqual(plan.safety, FixSafety.SAFE)

            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "VERIFIED")
            self.assertIn("version: 1.2.3+4", pubspec.read_text())

            report = build_report(target)
            version = next(f for f in report.findings if f.finding_id == "technical.pubspec_version")
            self.assertEqual(version.status, Status.PASS)


class AmbiguousYamlManualTests(unittest.TestCase):
    """D. ambiguous YAML -> MANUAL/no mutation."""

    def test_mismatched_quotes_around_invalid_version_stay_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("ambiguous_yaml_manual", directory)
            pubspec = target / "pubspec.yaml"
            before = pubspec.read_bytes()

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.fix_id == "manual.repair_yaml_pubspec_version")
            self.assertEqual(plan.safety, FixSafety.MANUAL)

            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(pubspec.read_bytes(), before)


class MalformedPlistSafeRepairTests(unittest.TestCase):
    """E. malformed plist safe repair."""

    def test_bare_ampersand_in_string_value_is_escaped(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("malformed_plist_safe_repair", directory)
            info = target / "ios/Runner/Info.plist"
            import plistlib
            with self.assertRaises(Exception):
                plistlib.loads(info.read_bytes())

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.fix_id == "safe.repair_plist_info_entities")
            self.assertEqual(plan.safety, FixSafety.SAFE)

            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "VERIFIED")
            self.assertIn("Salt &amp; Pepper", info.read_text())
            values = plistlib.loads(info.read_bytes())
            self.assertEqual(values["CFBundleDisplayName"], "Salt & Pepper")


class AmbiguousPlistManualTests(unittest.TestCase):
    """F. unsupported/ambiguous plist -> MANUAL/no mutation."""

    def test_raw_angle_bracket_in_string_value_stays_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("ambiguous_plist_manual", directory)
            info = target / "ios/Runner/Info.plist"
            before = info.read_bytes()

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.fix_id == "manual.repair_plist_info")
            self.assertEqual(plan.safety, FixSafety.MANUAL)

            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(info.read_bytes(), before)


class MissingScaffoldCreatesPlanTests(unittest.TestCase):
    """G. missing safe scaffold -> CREATE plan."""

    def test_missing_locale_directory_gets_an_auto_create_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("missing_localization_scaffold", directory)
            self.assertEqual(list(target.glob("ios/**/*.lproj")), [])

            plans = plan_fixes(target)
            plan = next(p for p in plans if p.fix_id == "safe.scaffold_default_locale")
            self.assertEqual(plan.safety, FixSafety.SAFE)
            self.assertEqual(plan.operation, FixOperation.CREATE)
            self.assertEqual(plan.target_path, "ios/Runner/en.lproj")


class ScaffoldDoesNotFabricateContentTests(unittest.TestCase):
    """H. scaffold creation does not fabricate content."""

    def test_created_locale_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("missing_localization_scaffold", directory)
            plan = next(p for p in plan_fixes(target) if p.fix_id == "safe.scaffold_default_locale")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "VERIFIED")
            created = target / "ios/Runner/en.lproj"
            self.assertTrue(created.is_dir())
            self.assertEqual(list(created.iterdir()), [])


class PlaceholderResolvesOnlyStructuralFindingTests(unittest.TestCase):
    """I. placeholder creation may resolve a structural finding but must not
    resolve a content-required finding."""

    def test_scaffold_flips_only_the_structural_localization_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("missing_localization_scaffold", directory)
            before_report = build_report(target)
            before_by_id = {f.finding_id: f for f in before_report.findings}
            self.assertNotEqual(before_by_id["metadata.localizations"].status, Status.PASS)
            # These require file content the scaffold never writes; confirm their
            # starting status so the "unchanged" assertion below is meaningful.
            self.assertNotEqual(before_by_id["metadata.infoplist_strings"].status, Status.PASS)
            self.assertNotEqual(before_by_id["metadata.localized_app_name"].status, Status.PASS)

            plan = next(p for p in plan_fixes(target) if p.fix_id == "safe.scaffold_default_locale")
            result = apply_plans(target, [plan])[0]
            self.assertEqual(result.status, "VERIFIED")

            after_report = build_report(target)
            after_by_id = {f.finding_id: f for f in after_report.findings}
            # Only the purely-structural (directory-presence) finding may flip to PASS.
            self.assertEqual(after_by_id["metadata.localizations"].status, Status.PASS)
            # Content-required / file-content findings must not be silently resolved
            # by an empty directory: their status is unchanged by the scaffold.
            for finding_id in ("metadata.infoplist_strings", "metadata.localized_app_name",
                               "metadata.privacy_policy", "metadata.support_url"):
                self.assertEqual(after_by_id[finding_id].status, before_by_id[finding_id].status,
                                 f"{finding_id} status changed from an empty scaffold directory")
            self.assertNotEqual(after_by_id["metadata.infoplist_strings"].status, Status.PASS)
            self.assertNotEqual(after_by_id["metadata.localized_app_name"].status, Status.PASS)


class DryRunRemainsZeroMutationTests(unittest.TestCase):
    """J. dry-run remains zero mutation, across every new fixture."""

    def test_plan_fixes_cli_is_zero_mutation_for_every_new_fixture(self):
        for name in (
            "malformed_json_recoverable", "malformed_json_ambiguous",
            "malformed_yaml_safe_repair", "ambiguous_yaml_manual",
            "malformed_plist_safe_repair", "ambiguous_plist_manual",
            "missing_localization_scaffold",
        ):
            with self.subTest(fixture=name), tempfile.TemporaryDirectory() as directory:
                target = copied_fixture(name, directory)
                before = all_hashes(target)
                result = subprocess.run(
                    [sys.executable, "scripts/readiness_check.py", str(target), "--plan-fixes"],
                    cwd=ROOT, capture_output=True, text=True,
                )
                after = all_hashes(target)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(before, after)


class NoAutoFixableProtectedRulesTests(unittest.TestCase):
    """N. Bundle ID/signing/privacy remain non-auto-fixable, even with the new planners registered."""

    def test_protected_rules_still_forbid_or_require_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copied_fixture("valid_flutter", directory)
            plans = plan_fixes(target)
            by_finding = {p.finding_id: p for p in plans if p.fix_id.startswith("guarded.")}
            self.assertEqual(by_finding["technical.entitlements"].safety, FixSafety.FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
