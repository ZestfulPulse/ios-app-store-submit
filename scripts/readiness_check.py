#!/usr/bin/env python3
"""Run read-only Phase 1 readiness checks for a Flutter/iOS project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_import() -> None:
    # Keep this script runnable directly from a source checkout without packaging.
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def main(argv: list[str] | None = None) -> int:
    _bootstrap_import()
    from ios_app_store_submit.readiness.report import build_report, human_summary, write_json

    parser = argparse.ArgumentParser(description="Read-only iOS App Store readiness inspection")
    parser.add_argument("project_path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json", help="print the JSON report")
    parser.add_argument("--output", type=Path, help="JSON output path")
    parser.add_argument("--strict", action="store_true", help="treat UNKNOWN findings as a failed gate")
    parser.add_argument("--pre-review", action="store_true", dest="pre_review",
                        help="run the offline Apple App Review Guidelines pre-review engine")
    parser.add_argument("--privacy", action="store_true",
                        help="run the offline, evidence-based App Privacy intelligence engine")
    parser.add_argument("--design", action="store_true",
                        help="run the offline, evidence-based HIG / Design Review engine")
    parser.add_argument("--design-evidence", type=Path, default=None,
                        help="optional path to a JSON file of supplied rendered-UI evidence (never captured automatically)")
    parser.add_argument("--rejection", type=Path, default=None,
                        help="path to a local rejection text/JSON file to run through the recovery engine")
    parser.add_argument("--resubmit-plan", type=Path, default=None,
                        help="read a local recovery report and build a closed-loop resubmission plan")
    parser.add_argument("--approve-resubmit", action="store_true",
                        help="record explicit local approval for the exact resubmission plan digest")
    parser.add_argument("--execute-resubmit", action="store_true",
                        help="execute one explicitly approved resubmission command and verify ASC state")
    parser.add_argument("--approval-digest", default=None,
                        help="exact plan digest bound to an approval or execution")
    parser.add_argument("--approved-by", default="explicit-user",
                        help="local approval actor label; no credential is stored")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-fixes", action="store_true", help="show fix proposals without changing the project")
    mode.add_argument("--apply-safe-fixes", action="store_true", help="apply SAFE proposals and verify each one")
    args = parser.parse_args(argv)

    project = args.project_path.expanduser().resolve()

    if args.resubmit_plan is not None:
        if args.approve_resubmit and args.execute_resubmit:
            parser.error("--approve-resubmit and --execute-resubmit are separate approval/execution steps")
        from ios_app_store_submit.resubmit.approval import (
            create_approval, load_approval, validate_approval, write_approval,
        )
        from ios_app_store_submit.resubmit.eligibility import evaluate_eligibility
        from ios_app_store_submit.resubmit.planner import load_recovery_report, plan_resubmission
        from ios_app_store_submit.resubmit.report import build_report as build_resubmit_report
        from ios_app_store_submit.resubmit.report import human_summary as resubmit_summary
        from ios_app_store_submit.resubmit.report import json_report as resubmit_json
        from ios_app_store_submit.resubmit.verifier import execute_resubmit

        try:
            recovery_report = load_recovery_report(args.resubmit_plan)
            plan = plan_resubmission(recovery_report)
            if args.approve_resubmit:
                if not args.approval_digest:
                    parser.error("--approve-resubmit requires --approval-digest")
                record = create_approval(plan, approval_digest=args.approval_digest, approved_by=args.approved_by)
                write_approval(project, record)
                plan = plan_resubmission(recovery_report, project_path=project)
            approval = load_approval(project)
            if args.execute_resubmit:
                if not args.approval_digest:
                    parser.error("--execute-resubmit requires --approval-digest")
                current_plan = plan_resubmission(recovery_report)
                execution = execute_resubmit(
                    plan, approval, approval_digest=args.approval_digest, current_plan=current_plan,
                )
            else:
                execution = None
            eligibility = evaluate_eligibility(recovery_report)
            closed_loop = build_resubmit_report(eligibility, plan, approval, execution)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"RESUBMIT_ERROR: {exc}", file=sys.stderr)
            return 2
        if args.as_json:
            print(resubmit_json(closed_loop))
        else:
            print(resubmit_summary(closed_loop))
            if plan.commands:
                print("\nCOMMANDS_PREVIEW:\n" + "\n".join(plan.commands))
            if plan.blockers:
                print("\nBLOCKERS:\n- " + "\n- ".join(plan.blockers))
        if args.execute_resubmit:
            return 0 if closed_loop.final == "RESUBMITTED_VERIFIED" else 1
        return 0 if closed_loop.plan_status == "READY" else 1

    report = build_report(project, strict=args.strict)
    output = args.output.expanduser() if args.output else project / ".asc" / "readiness-report.json"
    plans = ()
    executions = ()
    if args.plan_fixes or args.apply_safe_fixes:
        from ios_app_store_submit.readiness.fixes.planner import plan_fixes

        plans = plan_fixes(project, report)
    if args.apply_safe_fixes:
        from ios_app_store_submit.readiness.fixes.verifier import apply_plans

        executions = apply_plans(project, plans)
        report = build_report(project, strict=args.strict)

    pre_review = None
    if args.pre_review:
        from ios_app_store_submit.review.evaluator import run_pre_review

        pre_review = run_pre_review(project, readiness_report=report)

    privacy_result = None
    if args.privacy:
        from ios_app_store_submit.privacy.report import run_privacy_intelligence

        privacy_result = run_privacy_intelligence(project, readiness_report=report)

    design_result = None
    if args.design:
        from ios_app_store_submit.design.evaluator import run_design_review
        from ios_app_store_submit.design.report import load_design_evidence

        design_evidence = load_design_evidence(args.design_evidence) if args.design_evidence else None
        design_result = run_design_review(project, design_evidence=design_evidence)

    recovery_result = None
    if args.rejection:
        from ios_app_store_submit.recovery.report import run_recovery

        recovery_result = run_recovery(
            project, args.rejection, readiness_report=report, privacy_result=privacy_result,
            design_result=design_result,
        )

    # A default dry-run must not create .asc/readiness-report.json. An explicit
    # --output is an intentional report write and remains available in dry-run mode.
    if not args.plan_fixes or args.output is not None:
        write_json(report, output)
    payload = report.to_dict()
    if plans:
        payload["fix_plans"] = [plan.to_dict() for plan in plans]
    if executions:
        applied = [item for item in executions if item.status != "SKIPPED"]
        payload["applied_fixes"] = [item.to_dict() for item in applied]
        payload["verification_results"] = [
            {
                "fix_id": item.plan.fix_id,
                "verification_rule": item.plan.verification_rule,
                "verified": item.plan.verified,
                "result": item.status,
            }
            for item in applied
        ]
        payload["rollback_results"] = [
            {"fix_id": item.plan.fix_id, "rollback": item.rollback}
            for item in executions if item.rollback not in ("NOT_APPLICABLE", "NOT_NEEDED")
        ]
    if pre_review is not None:
        payload["pre_review"] = pre_review.gate
        payload["ruleset"] = pre_review.ruleset.to_dict()
        payload["review_findings"] = [item.to_dict() for item in pre_review.ordered_findings()]
        payload["review_summary"] = {
            "counts": pre_review.counts,
            "category_status": pre_review.category_status,
            "gate": pre_review.gate,
        }
    if privacy_result is not None:
        privacy_payload = privacy_result.to_dict()
        payload.update(privacy_payload)
    if design_result is not None:
        payload["design_review"] = design_result.gate
        design_payload = design_result.to_dict()
        payload["design_ruleset"] = design_payload["ruleset"]
        payload["design_findings"] = design_payload["design_findings"]
        payload["design_summary"] = design_payload["design_summary"]
    if recovery_result is not None:
        payload.update(recovery_result.to_dict())
    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        if recovery_result is not None:
            from ios_app_store_submit.recovery.report import human_summary as recovery_summary

            print(recovery_summary(recovery_result))
            print()
        if design_result is not None:
            from ios_app_store_submit.design.report import human_summary as design_summary

            print(design_summary(design_result))
            print()
        if privacy_result is not None:
            from ios_app_store_submit.privacy.report import human_summary as privacy_summary

            print(privacy_summary(privacy_result))
            print()
        if pre_review is not None:
            from ios_app_store_submit.review.evaluator import human_summary as pre_review_summary

            print(pre_review_summary(pre_review))
            print()
        print(human_summary(report))
        if args.plan_fixes or args.apply_safe_fixes:
            print("\nFIX_PLANS:")
            if plans:
                for plan in plans:
                    print(f"- {plan.fix_id} [{plan.safety.value}] {plan.title} -> {plan.target_path}")
            else:
                print("- None")
        if executions:
            print("\nFIX_RESULTS:")
            for execution in executions:
                print(f"- {execution.plan.fix_id} [{execution.status}] rollback={execution.rollback} {execution.message}")
    unsafe_outcome = any(item.status in ("FAILED_VERIFY", "STALE_PLAN", "FAILED_APPLY") for item in executions)
    pre_review_failed = pre_review is not None and (
        pre_review.gate == "BLOCKED" or (args.strict and pre_review.gate == "CONDITIONAL")
    )
    privacy_failed = privacy_result is not None and (
        privacy_result.gate == "BLOCKED" or (args.strict and privacy_result.gate == "CONDITIONAL")
    )
    design_failed = design_result is not None and (
        design_result.gate == "BLOCKED" or (args.strict and design_result.gate == "CONDITIONAL")
    )
    return 1 if (report.ready == "NO" or unsafe_outcome or pre_review_failed or privacy_failed
                 or design_failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
