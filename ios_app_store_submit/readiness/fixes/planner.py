"""Turn readiness findings into explicit, non-mutating fix plans."""

from __future__ import annotations

from pathlib import Path

from ..inspector import ProjectInspector
from ..models import Finding, ReadinessReport, Status
from ..report import build_report
from .models import FixOperation, FixPlan, FixSafety
from .safe_fixes import plan_localization_scaffold, plan_safe_fixes
from .structured_repair import plan_json_repairs, plan_plist_repairs, plan_yaml_repairs


PROTECTED_RULES = {
    "technical.bundle_id": (FixSafety.FORBIDDEN, "Bundle ID changes require explicit product/signing approval."),
    "technical.team_id": (FixSafety.FORBIDDEN, "Development team changes are signing configuration changes."),
    "technical.device_family": (FixSafety.APPROVAL_REQUIRED, "Device family changes affect product scope and require approval."),
    "technical.entitlements": (FixSafety.FORBIDDEN, "Entitlements/capabilities must never be auto-changed."),
    "technical.pbxproj": (FixSafety.FORBIDDEN, "project.pbxproj is outside the SAFE Phase 2 boundary."),
    "technical.signing": (FixSafety.FORBIDDEN, "Signing identities, certificates, and profiles cannot be auto-changed."),
    "technical.certificates": (FixSafety.FORBIDDEN, "Certificates cannot be auto-changed."),
    "technical.provisioning": (FixSafety.FORBIDDEN, "Provisioning profiles cannot be auto-changed."),
    "metadata.privacy_policy": (FixSafety.APPROVAL_REQUIRED, "Privacy URL changes require user-provided metadata and approval."),
    "metadata.support_url": (FixSafety.APPROVAL_REQUIRED, "Support URL changes require user-provided metadata and approval."),
    "metadata.app_privacy": (FixSafety.FORBIDDEN, "App Privacy declarations require the App Store Connect UI and explicit publish."),
    "reviewability.review_info": (FixSafety.APPROVAL_REQUIRED, "Review account/contact data must be supplied by the user."),
    "reviewability.review_notes": (FixSafety.APPROVAL_REQUIRED, "Review notes require user-provided content."),
    "reviewability.signing": (FixSafety.FORBIDDEN, "Signing identities, certificates, and profiles cannot be auto-changed."),
    "reviewability.pricing": (FixSafety.FORBIDDEN, "Pricing and availability are external state."),
    "reviewability.review_submission": (FixSafety.FORBIDDEN, "Review submission is an external mutation."),
}


def plan_for_finding(finding: Finding) -> FixPlan | None:
    protected = PROTECTED_RULES.get(finding.finding_id)
    if protected is None:
        return None
    safety, reason = protected
    return FixPlan(
        fix_id=f"guarded.{finding.finding_id.replace('.', '_')}",
        finding_id=finding.finding_id,
        safety=safety,
        title=f"Do not automatically change: {finding.title}",
        target_path=finding.source_path or "external state",
        before=finding.message,
        proposed_after=None,
        reason=reason,
        verification_rule=finding.finding_id,
        operation=FixOperation.UPDATE_FORMAT,
        rule_id=finding.rule_id,
        evidence=tuple(item.kind for item in finding.evidence),
        rollback_possible=False,
    )


def plan_fixes(project_path: str | Path, report: ReadinessReport | None = None) -> tuple[FixPlan, ...]:
    inspector = ProjectInspector(project_path)
    report = report or build_report(inspector.root)
    plans = plan_safe_fixes(inspector)
    plans.extend(plan_json_repairs(inspector))
    plans.extend(plan_yaml_repairs(inspector))
    plans.extend(plan_plist_repairs(inspector))
    plans.extend(plan_localization_scaffold(inspector))
    for finding in report.ordered_findings():
        if finding.status is Status.PASS:
            continue
        guarded = plan_for_finding(finding)
        if guarded is not None:
            plans.append(guarded)
    unique: dict[str, FixPlan] = {}
    for plan in plans:
        unique.setdefault(plan.fix_id, plan)
    return tuple(unique.values())
