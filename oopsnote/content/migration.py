"""Explicit, validation-first migration helpers for legacy problem content."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .oopsmark import ContentIssue, normalize_oopsmark, normalize_option_text, validate_oopsmark


@dataclass(frozen=True)
class LegacyProblemMigration:
    """A normalized candidate and the issues that prevent applying it."""

    fields: dict[str, Any]
    issues: tuple[ContentIssue, ...]

    @property
    def ready(self) -> bool:
        return not self.issues


def prepare_legacy_problem(problem: Mapping[str, Any]) -> LegacyProblemMigration:
    """Prepare a legacy problem for explicit OopsMark v1 validation.

    This function never changes persisted data. Invalid legacy constructs are
    returned as issues so a caller can report them without guessing a rewrite.
    """

    fields: dict[str, Any] = {
        "problem_text": normalize_oopsmark(str(problem.get("problem_text") or "")),
        "answer": normalize_oopsmark(str(problem.get("answer") or "")),
        "short_answer": normalize_oopsmark(str(problem.get("short_answer") or "")),
        "explanation": normalize_oopsmark(str(problem.get("explanation") or "")),
        "options": [normalize_option_text(str(option)) for option in problem.get("options", [])],
    }
    issues: list[ContentIssue] = []
    for field_name in ("problem_text", "answer", "short_answer", "explanation"):
        issues.extend(
            ContentIssue(
                code=issue.code,
                message=f"{field_name}: {issue.message}",
                line=issue.line,
                severity=issue.severity,
            )
            for issue in validate_oopsmark(fields[field_name])
        )
    for index, option in enumerate(fields["options"]):
        issues.extend(
            ContentIssue(
                code=issue.code,
                message=f"options[{index}]: {issue.message}",
                line=issue.line,
                severity=issue.severity,
            )
            for issue in validate_oopsmark(option)
        )
    return LegacyProblemMigration(fields=fields, issues=tuple(issues))


__all__ = ["LegacyProblemMigration", "prepare_legacy_problem"]
