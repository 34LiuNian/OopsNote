"""Task, run, upload, and problem mutation routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from oopsnote.api.schemas import UploadRequest
from oopsnote.core import (
    ContentFormat,
    Problem,
    QuestionType,
    TagDimension,
    TaskCreateRequest,
    TaskStatus,
)

router = APIRouter()


def _api():
    # Imported lazily so main remains the composition root and tests can replace
    # its local stores/runners without rebuilding the FastAPI application.
    from oopsnote.api import main

    return main


@router.get("/tasks")
def list_tasks(
    active_only: bool = False,
    status: Optional[TaskStatus] = None,
    subject: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    tasks = api.TASK_STORE.list_all()
    if active_only:
        tasks = [
            task
            for task in tasks
            if task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}
        ]
    if status:
        tasks = [task for task in tasks if task.status == status]
    if subject:
        tasks = [task for task in tasks if task.subject == subject]
    tasks.sort(key=lambda task: task.created_at, reverse=True)
    return {"items": [api._task_summary(task) for task in tasks[:limit]]}


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        return {"task": api._task_view(api.TASK_STORE.get(task_id))}
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")


@router.post("/tasks")
def create_task(payload: TaskCreateRequest) -> dict[str, Any]:
    api = _api()
    return {"task": api._task_view(api.TASK_STORE.create(payload))}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    api.TASK_STORE.delete(task_id)
    return {"success": True}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    run = api.RUN_STORE.active_for_task(task_id)
    api._runner_for(run.backend if run else api._configured_backend(None)).cancel(
        task_id
    )
    return {"task": api._task_view(api.TASK_STORE.get(task_id))}


def _enqueue(
    task_id: str,
    background_tasks: BackgroundTasks,
    backend: Optional[str],
) -> dict[str, Any]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    selected_backend = api._configured_backend(backend)
    runner = api._runner_for(selected_backend)
    runner.recover_stale()
    try:
        run = runner.enqueue(task_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))
    background_tasks.add_task(
        api._run_managed,
        task_id,
        run.id,
        selected_backend,
    )
    return {
        "task": api._task_view(api.TASK_STORE.get(task_id)),
        "run": api._run_view(run),
    }


@router.post("/tasks/{task_id}/process")
def process_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    backend: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    return _enqueue(task_id, background_tasks, backend)


@router.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    backend: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    return _enqueue(task_id, background_tasks, backend)


@router.get("/tasks/{task_id}/runs")
def list_task_runs(task_id: str) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    runs = [run for run in api.RUN_STORE.list_all() if run.task_id == task_id]
    runs.sort(key=lambda run: run.heartbeat_at, reverse=True)
    return {"items": [api._run_view(run) for run in runs]}


@router.patch("/tasks/{task_id}/problem/override")
def override_problem(
    task_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")

    problem = task.problem
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    question_type = problem.question_type
    if payload.get("question_type"):
        try:
            question_type = QuestionType(payload["question_type"])
        except ValueError:
            pass
    options = payload.get("options", problem.options)
    if options and isinstance(options[0], dict):
        options = [item.get("text", "") for item in options]
    content_format = problem.content_format
    if payload.get("content_format"):
        try:
            content_format = ContentFormat(payload["content_format"])
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Unsupported content_format",
            )
    try:
        updated_problem = Problem.model_validate(
            {
                **problem.model_dump(),
                "content_format": content_format,
                "problem_text": payload.get("problem_text", problem.problem_text),
                "options": options,
                "question_type": question_type,
                "source": payload.get("source") or problem.source,
                "knowledge_points": payload.get(
                    "knowledge_tags",
                    problem.knowledge_points,
                ),
                "error_hypothesis": payload.get(
                    "error_tags",
                    problem.error_hypothesis,
                ),
            }
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    task = api.TASK_STORE.set_problem(task_id, updated_problem)
    return {"task": api._task_view(task)}


@router.post("/tasks/{task_id}/problem/diagram")
def rerender_problem_diagram(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    return {"task": api._task_view(task)}


@router.post("/upload")
def upload_task(payload: UploadRequest) -> dict[str, Any]:
    api = _api()
    path = api.ASSET_STORE.save_base64(payload.image_base64, payload.filename)
    metadata = payload.model_dump(exclude={"image_base64", "filename", "mime_type"})
    metadata["mime_type"] = payload.mime_type
    trace: dict[str, Any] = {
        "kind": "single_image",
        "screenshot_path": path,
        "screenshot_filename": payload.filename,
    }
    if payload.batch_session_hash and payload.batch_segment_id:
        try:
            session = api.BATCH_SESSION_STORE.get(payload.batch_session_hash)
        except KeyError:
            session = None
        if session:
            trace = {
                "kind": "batch_segment",
                "source_file_hash": session.file_hash,
                "source_file_name": session.filename,
                "source_file_path": session.asset_path,
                "page_index": payload.batch_page_index,
                "question_no": payload.batch_question_no,
                "segment_id": payload.batch_segment_id,
                "screenshot_path": path,
                "screenshot_filename": payload.filename,
            }
    metadata["trace"] = trace
    task = api.TASK_STORE.create(
        TaskCreateRequest(
            subject=payload.subject,
            asset_path=path,
            tags=[
                *payload.knowledge_tags,
                *payload.error_tags,
                *payload.user_tags,
            ],
            metadata=metadata,
        )
    )
    api.TAG_STORE.ensure(
        TagDimension.META,
        [payload.source] if payload.source else [],
    )
    api.TAG_STORE.ensure(TagDimension.KNOWLEDGE, payload.knowledge_tags)
    api.TAG_STORE.ensure(TagDimension.ERROR, payload.error_tags)
    api.TAG_STORE.ensure(TagDimension.CUSTOM, payload.user_tags)
    return {"task": api._task_view(task)}


__all__ = ["router"]
