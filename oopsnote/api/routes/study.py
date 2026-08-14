"""Duplicate confirmation and targeted variation routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from oopsnote.core import TaskCreateRequest, TaskStatus, VariationRequest, problem_fingerprint

router = APIRouter()


def _api():
    from oopsnote.api import main

    return main.request_api()


def _task_with_problem(task_id: str):
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Task not found") from error
    if not task.problem:
        raise HTTPException(status_code=409, detail="Task has no completed problem")
    return task


class MergePayload(BaseModel):
    direction: Literal["into_current", "into_candidate"]


class VariationPayload(BaseModel):
    direction: Literal[
        "change_conditions",
        "add_distractors",
        "reverse_question",
        "change_context",
        "increase_complexity",
    ] = "change_conditions"
    custom_request: str = Field(default="", max_length=2000)
    difficulty: str | None = Field(default=None, max_length=80)
    count: int = Field(default=1, ge=1, le=5)


@router.get("/tasks/{task_id}/duplicates")
def list_duplicate_candidates(task_id: str) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    current = _task_with_problem(task_id)
    fingerprint = problem_fingerprint(current.problem)
    if not fingerprint:
        return {"items": []}
    items: list[dict[str, Any]] = []
    for candidate in api.TASK_STORE.list_all():
        if candidate.id == current.id or not candidate.problem:
            continue
        if problem_fingerprint(candidate.problem) != fingerprint:
            continue
        if api.PROBLEM_MERGE_STORE.canonical_for(candidate.problem.id) != candidate.problem.id:
            continue
        items.append(
            {
                "task": api._task_view(candidate),
                "source": api._problem_source(candidate, candidate.problem),
            }
        )
    items.sort(key=lambda item: item["task"]["created_at"], reverse=True)
    return {"items": items}


@router.post("/tasks/{task_id}/duplicates/{candidate_task_id}/merge")
def merge_duplicate(
    task_id: str,
    candidate_task_id: str,
    payload: MergePayload,
) -> dict[str, Any]:
    api = _api()
    current = _task_with_problem(task_id)
    candidate = _task_with_problem(candidate_task_id)
    if current.id == candidate.id:
        raise HTTPException(status_code=422, detail="Cannot merge a task into itself")
    if problem_fingerprint(current.problem) != problem_fingerprint(candidate.problem):
        raise HTTPException(status_code=409, detail="Only exact duplicate candidates can be merged")
    source, target = (
        (candidate.problem.id, current.problem.id)
        if payload.direction == "into_current"
        else (current.problem.id, candidate.problem.id)
    )
    try:
        record = api.PROBLEM_MERGE_STORE.merge(source, target)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"merge": record.model_dump(mode="json")}


@router.post("/tasks/{task_id}/variations")
def create_variations(task_id: str, payload: VariationPayload) -> dict[str, Any]:
    api = _api()
    parent = _task_with_problem(task_id)
    variation = VariationRequest(
        parent_problem_id=parent.problem.id,
        error_hypotheses=parent.problem.error_hypothesis,
        knowledge_points=parent.problem.knowledge_points,
        direction=payload.direction,
        custom_request=payload.custom_request.strip(),
        difficulty=payload.difficulty.strip() if payload.difficulty else None,
    )
    runner = api._runner_for(api._configured_backend())
    created = []
    for _ in range(payload.count):
        task = api.TASK_STORE.create(
            TaskCreateRequest(
                subject=parent.problem.subject or parent.subject,
                metadata={
                    "variation_request": variation.model_dump(mode="json"),
                    "variation_parent_problem": parent.problem.model_dump(mode="json"),
                    "parent_task_id": parent.id,
                    "error_tags": parent.problem.error_hypothesis,
                    "source": parent.problem.source or parent.metadata.get("source") or "",
                },
            )
        )
        try:
            run = runner.submit(task.id)
        except RuntimeError as error:
            api.TASK_STORE.mark_status(
                task.id,
                TaskStatus.FAILED,
                str(error),
                error_code="admission_conflict",
            )
            raise HTTPException(status_code=409, detail=str(error)) from error
        created.append(
            {"task": api._task_view(api.TASK_STORE.get(task.id)), "run": api._run_view(run)}
        )
    return {"items": created}


__all__ = ["router"]
