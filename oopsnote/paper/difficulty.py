"""Difficulty-coefficient inference and bounded automatic paper selection."""

from __future__ import annotations

import random
import re
from collections.abc import Iterable

from oopsnote.core import PaperDraftCreateRequest, PaperDraftItem, TaskRecord, subjects_match

from .defaults import default_points_for

QUESTION_TYPE_ORDER = {
    "单选题": 0,
    "多选题": 1,
    "填空题": 2,
    "解答题": 3,
}

DIFFICULTY_BOUNDS = {
    "easy": (0.0, 0.5),
    "medium": (0.5, 0.8),
    "hard": (0.8, 1.0),
}


def _question_number(task: TaskRecord) -> int | None:
    match = re.search(r"\d+", task.effective_question_no() or "")
    return int(match.group()) if match else None


def _source_key(task: TaskRecord) -> str | None:
    trace = task.metadata.get("trace")
    if isinstance(trace, dict) and trace.get("source_file_hash"):
        return f"batch:{trace['source_file_hash']}"
    if task.metadata.get("batch_session_hash"):
        return f"batch:{task.metadata['batch_session_hash']}"
    source = (task.problem.source if task.problem else "") or task.metadata.get("source")
    return f"source:{source.strip()}" if isinstance(source, str) and source.strip() else None


def subject_matches(candidate: str, requested: str) -> bool:
    return subjects_match(candidate, requested)


def difficulty_review_reason(task: TaskRecord) -> str | None:
    """Explain why a task needs manual difficulty classification, if any."""

    if task.difficulty_coefficient_override is not None:
        return None
    if not task.problem:
        return "missing_problem"
    if not _source_key(task):
        return "missing_source"
    number = _question_number(task)
    if number is None:
        return "missing_question_no"
    if task.section_question_count is None:
        return "missing_section_question_count"
    if number > task.section_question_count:
        return "question_no_exceeds_section_question_count"
    return None


def infer_difficulty_coefficients(tasks: Iterable[TaskRecord]) -> dict[str, float]:
    """Return task-id coefficients from explicit question number / section size."""

    coefficients: dict[str, float] = {}
    for task in tasks:
        if not task.problem:
            continue
        if task.difficulty_coefficient_override is not None:
            coefficients[task.id] = task.difficulty_coefficient_override
            continue
        if difficulty_review_reason(task) is not None:
            continue
        number = _question_number(task)
        if number is not None and task.section_question_count is not None:
            coefficients[task.id] = round(number / task.section_question_count, 6)
    return coefficients


def difficulty_band(coefficient: float | None) -> str | None:
    if coefficient is None:
        return None
    if coefficient <= DIFFICULTY_BOUNDS["easy"][1]:
        return "easy"
    if coefficient <= DIFFICULTY_BOUNDS["medium"][1]:
        return "medium"
    return "hard"


def _allocate(total: int, distribution: dict[str, int]) -> dict[str, int]:
    bands = ("easy", "medium", "hard")
    weights = [max(0, distribution.get(band, 0)) for band in bands]
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return {band: 0 for band in bands}
    raw = [total * weight / weight_sum for weight in weights]
    allocated = [int(value) for value in raw]
    remainder = total - sum(allocated)
    order = sorted(range(len(bands)), key=lambda index: raw[index] - allocated[index], reverse=True)
    for index in order[:remainder]:
        allocated[index] += 1
    return dict(zip(bands, allocated, strict=True))


def _candidate_tasks(
    tasks: Iterable[TaskRecord],
    *,
    subject: str,
    knowledge_tags: list[str],
) -> list[TaskRecord]:
    selected_tags = set(knowledge_tags)
    candidates = []
    for task in tasks:
        problem = task.problem
        if not problem or not subject_matches(problem.subject or task.subject, subject):
            continue
        if selected_tags and not selected_tags.intersection(problem.knowledge_points):
            continue
        candidates.append(task)
    return candidates


def select_paper_items(
    tasks: Iterable[TaskRecord],
    payload: PaperDraftCreateRequest,
    *,
    random_source: random.Random | None = None,
) -> list[PaperDraftItem]:
    """Select only candidates that satisfy the requested type and difficulty slots."""

    task_list = list(tasks)
    coefficients = infer_difficulty_coefficients(task_list)
    candidates = _candidate_tasks(
        task_list,
        subject=payload.subject,
        knowledge_tags=payload.knowledge_tags,
    )
    rng = random_source or random.SystemRandom()
    selected: list[PaperDraftItem] = []

    for question_type in sorted(
        payload.requested_counts, key=lambda value: QUESTION_TYPE_ORDER.get(value, 99)
    ):
        requested = max(0, payload.requested_counts.get(question_type, 0))
        allocation = _allocate(requested, payload.difficulty_distribution)
        type_candidates = [
            task
            for task in candidates
            if task.problem and task.problem.question_type.value == question_type
        ]
        type_ordinal = 0
        for band in ("easy", "medium", "hard"):
            band_candidates = [
                task
                for task in type_candidates
                if difficulty_band(coefficients.get(task.id)) == band
            ]
            rng.shuffle(band_candidates)
            for task in band_candidates[: allocation[band]]:
                selected.append(
                    PaperDraftItem(
                        task_id=task.id,
                        problem_id=task.problem.id,
                        question_type=question_type,
                        difficulty_coefficient=coefficients.get(task.id),
                        points=default_points_for(question_type, type_ordinal),
                    )
                )
                type_ordinal += 1

    return sorted(
        selected,
        key=lambda item: (
            QUESTION_TYPE_ORDER.get(item.question_type, 99),
            item.difficulty_coefficient if item.difficulty_coefficient is not None else 2,
        ),
    )


def candidate_tasks(
    tasks: Iterable[TaskRecord],
    *,
    subject: str,
    knowledge_tags: list[str],
) -> list[tuple[TaskRecord, float | None]]:
    task_list = list(tasks)
    coefficients = infer_difficulty_coefficients(task_list)
    candidates = _candidate_tasks(task_list, subject=subject, knowledge_tags=knowledge_tags)
    return sorted(
        ((task, coefficients.get(task.id)) for task in candidates),
        key=lambda pair: (
            QUESTION_TYPE_ORDER.get(pair[0].problem.question_type.value, 99),
            pair[1] if pair[1] is not None else 2,
        ),
    )
