"""Apply only SAFE plans and verify the exact originating readiness rule."""

from __future__ import annotations

import difflib
import hashlib
import json
import plistlib
from dataclasses import dataclass
from pathlib import Path

from ..report import build_report
from .models import FixPlan, FixSafety

NON_AUTO_FINDINGS = {
    "technical.bundle_id",
    "technical.team_id",
    "technical.signing",
    "technical.certificates",
    "technical.provisioning",
    "metadata.app_privacy",
    "reviewability.signing",
    "reviewability.pricing",
    "reviewability.review_submission",
}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class FixExecution:
    plan: FixPlan
    status: str
    diff: str = ""
    message: str = ""
    before_hash: str | None = None
    after_hash: str | None = None
    rollback: str = "NOT_APPLICABLE"

    def to_dict(self) -> dict[str, object]:
        return {
            "fix_id": self.plan.fix_id,
            "plan": self.plan.to_dict(),
            "status": self.status,
            "diff": self.diff,
            "message": self.message,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "verification_rule": self.plan.verification_rule,
            "rollback": self.rollback,
        }


def _rule_passes_for_target(project_path: str | Path, rule_id: str, target_path: str) -> bool:
    report = build_report(project_path)
    finding = next((item for item in report.findings if item.finding_id == rule_id), None)
    if finding is None or finding.status.value != "PASS":
        return False
    # A rule passing is not enough: it must be passing because of the file this
    # plan actually touched, not some unrelated file the rule happens to also read.
    return finding.source_path == target_path


def verify_fix(plan: FixPlan, project_path: str | Path) -> tuple[bool, str]:
    """Return (passed, explanation) after re-running the originating rule."""
    if plan.verification_rule in {"technical.pubspec_version", "metadata.display_name"}:
        passed = _rule_passes_for_target(project_path, plan.verification_rule, plan.target_path)
        return passed, "Originating readiness rule passed for the changed file." if passed else "Originating readiness rule did not pass for the changed file."
    if plan.verification_rule.startswith("scaffold:"):
        target = Path(project_path).expanduser().resolve() / plan.target_path
        passed = target.is_dir()
        return passed, "Scaffold directory exists." if passed else "Scaffold directory was not created."
    if plan.verification_rule.startswith("structured.json_valid:"):
        relative = plan.verification_rule.split(":", 1)[1]
        target = Path(project_path).expanduser().resolve() / relative
        try:
            json.loads(target.read_text(encoding="utf-8"))
            return True, "Target JSON file now parses."
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False, "Target JSON file still fails to parse."
    if plan.verification_rule.startswith("structured.plist_valid:"):
        relative = plan.verification_rule.split(":", 1)[1]
        target = Path(project_path).expanduser().resolve() / relative
        try:
            plistlib.loads(target.read_bytes())
            return True, "Target plist file now parses."
        except Exception:
            return False, "Target plist file still fails to parse."
    return False, f"No verifier is registered for {plan.verification_rule}."


def verify_plan(plan: FixPlan, project_path: str | Path) -> bool:
    passed, _ = verify_fix(plan, project_path)
    return passed


def _inside(root: Path, relative_path: str) -> Path | None:
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def apply_plans(project_path: str | Path, plans: tuple[FixPlan, ...] | list[FixPlan]) -> tuple[FixExecution, ...]:
    root = Path(project_path).expanduser().resolve()
    results: list[FixExecution] = []
    for plan in plans:
        if plan.safety is not FixSafety.SAFE or plan.finding_id in NON_AUTO_FINDINGS:
            plan.verification_result = "SKIPPED"
            results.append(FixExecution(plan, "SKIPPED", message=f"Safety boundary: {plan.safety.value}."))
            continue
        target = _inside(root, plan.target_path)
        if target is None or target.name == "project.pbxproj" or plan.target_path.endswith(".mobileprovision"):
            plan.verification_result = "SKIPPED"
            results.append(FixExecution(plan, "SKIPPED", message="Target is outside the SAFE file boundary."))
            continue

        if plan.before is None and plan.proposed_after == "<empty directory created>":
            if target.exists():
                # The plan assumed the directory was absent; that assumption no
                # longer holds, so nothing is created.
                plan.verification_result = "STALE_PLAN"
                results.append(FixExecution(
                    plan, "STALE_PLAN",
                    message="Scaffold target now exists; the planning assumption no longer holds.",
                    rollback="NOT_APPLICABLE",
                ))
                continue
            target.mkdir(parents=True, exist_ok=False)
            passed, message = verify_fix(plan, root)
            if passed:
                plan.applied = True
                plan.verified = True
                plan.verification_result = "VERIFIED"
                results.append(FixExecution(plan, "VERIFIED", message=message, rollback="NOT_NEEDED"))
            else:
                target.rmdir()
                plan.verification_result = "FAILED_VERIFY"
                results.append(FixExecution(plan, "FAILED_VERIFY", message=message, rollback="ROLLED_BACK"))
            continue

        try:
            before_bytes = target.read_bytes()
            before_text = before_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            plan.verification_result = "FAILED_APPLY"
            results.append(FixExecution(plan, "FAILED_APPLY", message=str(exc)))
            continue

        before_hash = _hash(before_bytes)
        if not isinstance(plan.before, str) or not isinstance(plan.proposed_after, str) or plan.before not in before_text:
            # The target drifted from the state the plan was built against:
            # capture that here and stop before any write happens.
            plan.verification_result = "STALE_PLAN"
            results.append(FixExecution(
                plan, "STALE_PLAN",
                message="Planned before-value no longer matches the target; the plan is stale.",
                before_hash=before_hash, rollback="NOT_APPLICABLE",
            ))
            continue

        after_text = before_text.replace(plan.before, plan.proposed_after, 1)
        after_bytes = after_text.encode("utf-8")
        diff = "".join(difflib.unified_diff(
            before_text.splitlines(keepends=True), after_text.splitlines(keepends=True),
            fromfile=plan.target_path, tofile=plan.target_path,
        ))
        try:
            target.write_bytes(after_bytes)
        except OSError as exc:
            plan.verification_result = "FAILED_APPLY"
            results.append(FixExecution(plan, "FAILED_APPLY", diff=diff, message=str(exc), before_hash=before_hash))
            continue

        after_hash = _hash(after_bytes)
        passed, message = verify_fix(plan, root)
        if passed:
            plan.applied = True
            plan.verified = True
            plan.verification_result = "VERIFIED"
            results.append(FixExecution(
                plan, "VERIFIED", diff=diff, message=message,
                before_hash=before_hash, after_hash=after_hash, rollback="NOT_NEEDED",
            ))
        else:
            rollback_status = "ROLLBACK_FAILED"
            if plan.rollback_possible:
                try:
                    target.write_bytes(before_bytes)
                    rollback_status = "ROLLED_BACK" if _hash(target.read_bytes()) == before_hash else "ROLLBACK_FAILED"
                except OSError:
                    rollback_status = "ROLLBACK_FAILED"
            plan.verification_result = "FAILED_VERIFY"
            results.append(FixExecution(
                plan, "FAILED_VERIFY", diff=diff, message=message,
                before_hash=before_hash, after_hash=after_hash, rollback=rollback_status,
            ))
    return tuple(results)
