"""Guarded execution and post-submit verification.

The only mutating call in this module is the one exact command selected by an
already approved plan.  A failed command is returned immediately; there is no
automatic retry or fallback mutation.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, Callable, Iterable, Mapping

from .approval import validate_approval
from .models import (
    ApprovalRecord, ExecutionResult, ExecutionStatus, PostSubmitVerification, ResubmitPlan, ResubmitStatus,
)


DEFAULT_ACCEPTED_STATES = frozenset({
    # These are the only post-submit review states supported by the current
    # project evidence: the bundled skill documents WAITING_FOR_REVIEW and
    # the public v2 documentation also documents IN_REVIEW.  READY_FOR_REVIEW
    # is used for submission-item readiness, not post-submit review status;
    # SUBMITTED and PENDING_REVIEW have no verified evidence here.
    "WAITING_FOR_REVIEW", "IN_REVIEW",
})

# Reported state names are parsed separately from the accepted set so an
# unsupported but recognizable state can be returned as an explicit failure.
KNOWN_POST_SUBMIT_STATES = frozenset({
    "WAITING_FOR_REVIEW", "IN_REVIEW", "READY_FOR_REVIEW", "SUBMITTED", "PENDING_REVIEW",
})


def _state_from(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("reviewState", "review_state", "state", "status"):
            if value.get(key) not in (None, ""):
                return str(value[key]).upper()
        for key in ("data", "attributes", "result"):
            if key in value:
                found = _state_from(value[key])
                if found:
                    return found
        return None
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        text = value.strip()
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if loaded is not None:
            return _state_from(loaded)
        upper = text.upper()
        for candidate in sorted(KNOWN_POST_SUBMIT_STATES, key=len, reverse=True):
            if candidate in upper:
                return candidate
    return None


def verify_post_submit_state(state: Any, *, accepted_states: Iterable[str] = DEFAULT_ACCEPTED_STATES) -> PostSubmitVerification:
    normalized = _state_from(state)
    accepted = {str(item).upper() for item in accepted_states}
    if normalized is None:
        return PostSubmitVerification(None, False, "no ASC review state evidence", "post-submit state is UNKNOWN")
    if normalized in accepted:
        return PostSubmitVerification(normalized, True, "read-only ASC review status", "post-submit review state verified")
    return PostSubmitVerification(normalized, False, "read-only ASC review status", f"unexpected post-submit state: {normalized}")


def verify_execution(returncode: int, post_state: Any) -> ExecutionResult:
    verification = verify_post_submit_state(post_state)
    if returncode != 0:
        return ExecutionResult(
            status=ExecutionStatus.FAILED, returncode=returncode, post_submit=verification,
            message="submission command failed; no retry was attempted",
        )
    if not verification.verified:
        return ExecutionResult(
            status=ExecutionStatus.FAILED, returncode=returncode, post_submit=verification,
            message="command returned zero but post-submit state was not verified",
        )
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS, returncode=returncode, post_submit=verification,
        message="submission command succeeded and post-submit state was verified",
    )


def _completed(result: Any) -> tuple[int, str]:
    if isinstance(result, int):
        return result, ""
    if isinstance(result, Mapping):
        return int(result.get("returncode", 0)), str(result.get("stdout", "") or "")
    if isinstance(result, tuple) and len(result) >= 2:
        return int(result[0]), str(result[1] or "")
    return int(getattr(result, "returncode", 1)), str(getattr(result, "stdout", "") or "")


def _default_runner(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def execute_resubmit(
    plan: ResubmitPlan, approval: ApprovalRecord | None, *, approval_digest: str | None = None,
    current_plan: ResubmitPlan | None = None, runner: Callable[[list[str]], Any] | None = None,
    status_reader: Callable[[list[str]], Any] | None = None,
) -> ExecutionResult:
    """Execute exactly one approved mutation, then require state evidence."""

    valid, blockers = validate_approval(plan, approval, approval_digest=approval_digest)
    if current_plan is not None and (
        not current_plan.digest_valid or current_plan.computed_digest != plan.plan_digest
    ):
        valid = False
        blockers = tuple(sorted(set(blockers) | {"stale_plan"}))
    if not plan.ready:
        valid = False
        blockers = tuple(sorted(set(blockers) | {"plan_not_ready"}))
    if plan.eligibility is not ResubmitStatus.YES:
        valid = False
        blockers = tuple(sorted(set(blockers) | {"eligibility_not_yes"}))
    if not plan.selected_command:
        valid = False
        blockers = tuple(sorted(set(blockers) | {"missing_execution_command"}))
    if not valid:
        return ExecutionResult(status=ExecutionStatus.NOT_RUN, message="execution blocked: " + ", ".join(blockers))

    run = runner or _default_runner
    command = plan.selected_command
    result = run(shlex.split(command))
    returncode, stdout = _completed(result)
    if returncode != 0:
        return ExecutionResult(
            status=ExecutionStatus.FAILED, command=command, returncode=returncode,
            message="submission command failed; no retry was attempted",
        )

    reader = status_reader
    if reader is None:
        reader = run
    status_result = reader(shlex.split(f"asc review status --app {shlex.quote(str(plan.app_id))}"))
    status_code, status_output = _completed(status_result)
    state_source: Any = status_output
    if isinstance(status_result, Mapping):
        state_source = status_result
    verification = verify_post_submit_state(state_source)
    if status_code != 0:
        verification = PostSubmitVerification(
            verification.state, False, verification.evidence, "ASC status verification command failed",
        )
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS if verification.verified else ExecutionStatus.FAILED,
        command=command, returncode=returncode, post_submit=verification,
        message=("submission command succeeded and post-submit state was verified"
                  if verification.verified else "command succeeded but post-submit state was not verified"),
    )


def execute_plan(*args: Any, **kwargs: Any) -> ExecutionResult:
    return execute_resubmit(*args, **kwargs)


def verify_post_submission_state(state: Any, **kwargs: Any) -> PostSubmitVerification:
    return verify_post_submit_state(state, **kwargs)


__all__ = [
    "DEFAULT_ACCEPTED_STATES", "execute_plan", "execute_resubmit", "verify_execution",
    "verify_post_submit_state", "verify_post_submission_state",
]
