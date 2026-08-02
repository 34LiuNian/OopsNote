"""Deterministic problem identity helpers owned by Core."""

from __future__ import annotations

import hashlib
import json
import re

from .models import Problem


def problem_fingerprint(problem: Problem) -> str | None:
    """Return an exact-content fingerprint, or None for an empty problem."""
    if not problem.problem_text.strip():
        return None

    def compact(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    payload = {
        "subject": compact(problem.subject),
        "question_type": problem.question_type.value,
        "problem_text": compact(problem.problem_text),
        "options": [compact(option) for option in problem.options],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
