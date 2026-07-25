"""Difficulty-coefficient inference and bounded automatic paper selection."""

from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import Iterable, Optional

from oopsnote.core import PaperDraftCreateRequest, PaperDraftItem, TaskRecord


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

SUBJECT_ALIASES = {
    "math": {"math", "数学"},
    "physics": {"physics", "物理"},
    "chemistry": {"chemistry", "化学"},
    "biology": {"biology", "生物"},
    "english": {"english", "英语"},
}


def _question_number(task: TaskRecord) -> Optional[int]:
    raw = task.metadata.get("question_no")
    trace = task.metadata.get("trace")
    if raw is None and isinstance(trace, dict):
        raw = trace.get("question_no")
    match = re.search(r"\d+", str(raw or ""))
    return int(match.group()) if match else None


def _source_key(task: TaskRecord) -> Optional[str]:
    trace = task.metadata.get("trace")
    if isinstance(trace, dict) and trace.get("source_file_hash"):
        return f"batch:{trace['source_file_hash']}"
    if task.metadata.get("batch_session_hash"):
        return f"batch:{task.metadata['batch_session_hash']}"
    source = (task.problem.source if task.problem else "") or task.metadata.get("source")
    return f"source:{source.strip()}" if isinstance(source, str) and source.strip() else None


def _chapter_key(task: TaskRecord) -> str:
    return str(
        task.metadata.get("chapter")
        or task.metadata.get("source_chapter")
        or ""
    ).strip()


def subject_matches(candidate: str, requested: str) -> bool:
    requested_values = SUBJECT_ALIASES.get(requested, {requested})
    return candidate in requested_values


def infer_difficulty_coefficients(tasks: Iterable[TaskRecord]) -> dict[str, float]:
    """Return task-id coefficients using rank / observed section size.

    A section is scoped to source, optional chapter metadata, and question type.
    Missing source or question numbers intentionally remain unclassified.
    """

    grouped: dict[tuple[str, str, str], list[tuple[int, TaskRecord]]] = defaultdict(list)
    for task in tasks:
        if not task.problem:
            continue
        source_key = _source_key(task)
        number = _question_number(task)
        if not source_key or number is None:
            continue
        grouped[(source_key, _chapter_key(task), task.problem.question_type.value)].append(
            (number, task)
        )

    coefficients: dict[str, float] = {}
    for members in grouped.values():
        distinct_numbers = sorted({number for number, _ in members})
        rank_by_number = {
            number: (index + 1) / len(distinct_numbers)
            for index, number in enumerate(distinct_numbers)
        }
        for number, task in members:
            coefficients[task.id] = round(rank_by_number[number], 6)
    return coefficients


def difficulty_band(coefficient: Optional[float]) -> Optional[str]:
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
    return dict(zip(bands, allocated))


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
    random_source: Optional[random.Random] = None,
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

    for question_type in sorted(payload.requested_counts, key=lambda value: QUESTION_TYPE_ORDER.get(value, 99)):
        requested = max(0, payload.requested_counts.get(question_type, 0))
        allocation = _allocate(requested, payload.difficulty_distribution)
        type_candidates = [
            task for task in candidates
            if task.problem and task.problem.question_type.value == question_type
        ]
        for band in ("easy", "medium", "hard"):
            band_candidates = [
                task for task in type_candidates
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
                    )
                )

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
) -> list[tuple[TaskRecord, Optional[float]]]:
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
