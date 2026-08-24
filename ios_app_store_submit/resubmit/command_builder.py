"""Build exact ASC command previews; never execute them."""

from __future__ import annotations

import shlex
from typing import Any

from .models import CommandSet, ResubmitPlan


def _quoted(value: str) -> str:
    return shlex.quote(value)


def build_commands(
    *, app_id: str | None, version: str | None, build_id: str | None, submission_id: str | None,
) -> CommandSet:
    missing = tuple(f"missing_{name}" for name, value in (
        ("app_id", app_id), ("version", version), ("build_id", build_id), ("submission_id", submission_id),
    ) if value is None or not str(value).strip())
    if missing:
        return CommandSet(blockers=missing, preview="BLOCKED: " + ", ".join(missing))

    primary = (
        f"asc review submit --app {_quoted(str(app_id))} --version {_quoted(str(version))} "
        f"--build {_quoted(str(build_id))} --confirm"
    )
    fallback = f"asc review submissions-submit --id {_quoted(str(submission_id))} --confirm"
    preview = "PRIMARY (execute at most this one):\n" + primary + "\nFALLBACK (use only if explicitly selected):\n" + fallback
    return CommandSet(commands=(primary, fallback), selected_command=primary, preview=preview)


def command_preview(plan: ResubmitPlan) -> CommandSet:
    return CommandSet(
        commands=plan.commands, selected_command=plan.selected_command,
        preview="\n".join(plan.commands), blockers=plan.blockers,
    )


class CommandBuilder:
    """Small OO facade retained for callers that prefer a builder instance."""

    def build(self, **kwargs: Any) -> CommandSet:
        if "plan" in kwargs:
            plan = kwargs["plan"]
            return command_preview(plan)
        return build_commands(**kwargs)


def build_resubmit_commands(**kwargs: Any) -> CommandSet:
    return build_commands(**kwargs)


__all__ = ["CommandBuilder", "build_commands", "build_resubmit_commands", "command_preview"]
