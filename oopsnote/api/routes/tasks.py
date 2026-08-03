"""Task, run, upload, and problem mutation routes."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

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
        task = api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.active_run_id or task.status == TaskStatus.PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="Cancel the active task before deleting it",
        )
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
    try:
        api._runner_for(run.backend if run else api._configured_backend(None)).cancel(
            task_id
        )
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"task": api._task_view(api.TASK_STORE.get(task_id))}


def _enqueue(
    task_id: str,
    backend: Optional[str],
    profile_id: Optional[str] = None,
) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    selected_backend = api._configured_backend(backend)
    if profile_id is not None:
        if selected_backend != "langchain":
            raise HTTPException(status_code=422, detail="profile_id requires the langchain backend")
        profile = next(
            (item for item in api.APP_SETTINGS_STORE.provider_profiles() if item.id == profile_id),
            None,
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="provider profile not found")
        if not profile.enabled or not profile.credential_ref:
            raise HTTPException(status_code=409, detail="provider profile is disabled or has no credential")
        try:
            has_secret = api.get_secret_store().has(profile.credential_ref)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail="provider secret store is unavailable") from error
        if not has_secret:
            raise HTTPException(status_code=409, detail="provider profile has no credential")
        api.TASK_STORE.update(
            task_id,
            metadata={**task.metadata, "ai_provider_profile_id": profile.id},
        )
    runner = api._runner_for(selected_backend)
    runner.recover_stale()
    try:
        run = runner.submit(task_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))
    return {
        "task": api._task_view(api.TASK_STORE.get(task_id)),
        "run": api._run_view(run),
    }


@router.post("/tasks/{task_id}/process")
def process_task(
    task_id: str,
    backend: Optional[str] = Query(default=None),
    profile_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
) -> dict[str, Any]:
    return _enqueue(task_id, backend, profile_id)


@router.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: str,
    backend: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    return _enqueue(task_id, backend)


@router.get("/tasks/{task_id}/runs")
def list_task_runs(task_id: str) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    runs = api.RUN_STORE.list_for_task(task_id)
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
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Unsupported question_type") from error
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
    next_metadata = dict(task.metadata)
    if "question_no" in payload:
        next_metadata["question_no"] = payload.get("question_no")
    if "chapter" in payload:
        raw_chapter = payload.get("chapter")
        if raw_chapter is not None and not isinstance(raw_chapter, str):
            raise HTTPException(status_code=422, detail="chapter must be a string or null")
        chapter = raw_chapter.strip() if raw_chapter else None
        if chapter and len(chapter) > 160:
            raise HTTPException(status_code=422, detail="chapter must be at most 160 characters")
        next_metadata["chapter"] = chapter
    if "user_tags" in payload:
        next_metadata["user_tags"] = list(payload.get("user_tags") or [])
    if "source" in payload:
        next_metadata["source"] = payload.get("source") or ""
    difficulty_coefficient_override = task.difficulty_coefficient_override
    if "difficulty_coefficient_override" in payload:
        raw_override = payload.get("difficulty_coefficient_override")
        if raw_override is None:
            difficulty_coefficient_override = None
        elif isinstance(raw_override, bool) or not isinstance(raw_override, (int, float)):
            raise HTTPException(
                status_code=422,
                detail="difficulty_coefficient_override must be a number or null",
            )
        elif not math.isfinite(raw_override) or not 0 <= raw_override <= 1:
            raise HTTPException(
                status_code=422,
                detail="difficulty_coefficient_override must be between 0 and 1",
            )
        else:
            difficulty_coefficient_override = float(raw_override)
    section_question_count = task.section_question_count
    if "section_question_count" in payload:
        raw_total = payload.get("section_question_count")
        if raw_total is None:
            section_question_count = None
        elif isinstance(raw_total, bool) or not isinstance(raw_total, int) or raw_total < 1:
            raise HTTPException(
                status_code=422,
                detail="section_question_count must be a positive integer or null",
            )
        else:
            section_question_count = raw_total
    diagram_fields = {
        "diagram_detected",
        "diagram_kind",
        "diagram_tikz_source",
        "diagram_svg",
        "diagram_image_path",
        "diagram_image_crop",
        "diagram_image_tone",
        "diagram_position",
        "diagram_scale_percent",
        "diagram_render_status",
        "diagram_error",
        "diagram_needs_review",
    }
    if diagram_fields.intersection(payload):
        diagram_detected = bool(payload.get("diagram_detected", next_metadata.get("diagram_detected", problem.has_diagram)))
        diagram_kind = payload.get("diagram_kind", next_metadata.get("diagram_kind"))
        if not diagram_detected:
            diagram_kind = None
        if diagram_kind not in {None, "tikz", "image"}:
            raise HTTPException(status_code=422, detail="diagram_kind must be tikz, image, or null")

        diagram_position = payload.get("diagram_position", next_metadata.get("diagram_position", "right"))
        if diagram_position not in {"left", "right"}:
            raise HTTPException(status_code=422, detail="diagram_position must be left or right")

        diagram_scale = payload.get("diagram_scale_percent", next_metadata.get("diagram_scale_percent"))
        if diagram_scale is not None:
            if isinstance(diagram_scale, bool) or not isinstance(diagram_scale, (int, float)):
                raise HTTPException(status_code=422, detail="diagram_scale_percent must be a number or null")
            diagram_scale = round(diagram_scale)
            if diagram_scale < 50 or diagram_scale > 200:
                raise HTTPException(status_code=422, detail="diagram_scale_percent must be between 50 and 200")

        next_metadata.update(
            {
                "diagram_detected": diagram_detected,
                "diagram_kind": diagram_kind,
                "diagram_position": diagram_position,
                "diagram_scale_percent": diagram_scale,
            }
        )
        if diagram_kind == "tikz":
            tikz_source = str(payload.get("diagram_tikz_source") or "").strip()
            if diagram_detected and not tikz_source:
                raise HTTPException(status_code=422, detail="TikZ diagrams require diagram_tikz_source")
            next_metadata.update(
                {
                    "diagram_tikz_source": tikz_source or None,
                    "diagram_svg": payload.get("diagram_svg"),
                    "diagram_image_path": None,
                    "diagram_image_crop": None,
                    "diagram_image_tone": None,
                    "diagram_render_status": payload.get("diagram_render_status"),
                    "diagram_error": payload.get("diagram_error"),
                    "diagram_needs_review": bool(payload.get("diagram_needs_review", False)),
                }
            )
        elif diagram_kind == "image":
            crop_was_provided = "diagram_image_crop" in payload
            crop = payload.get("diagram_image_crop") if crop_was_provided else None
            if crop_was_provided and crop is None:
                image_path = task.asset_path
            elif crop is not None:
                if not task.asset_path:
                    raise HTTPException(status_code=422, detail="Image diagrams require a task image asset")
                try:
                    image_path, crop = api.ASSET_STORE.save_image_crop(task.asset_path, crop)
                except (FileNotFoundError, ValueError) as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
            else:
                image_path = payload.get("diagram_image_path") or next_metadata.get("diagram_image_path") or task.asset_path
            if diagram_detected and not image_path:
                raise HTTPException(status_code=422, detail="Image diagrams require a task image asset")
            allowed_paths = {task.asset_path, next_metadata.get("diagram_image_path")}
            if image_path and image_path not in allowed_paths and crop is None:
                raise HTTPException(status_code=422, detail="diagram_image_path must belong to this task")
            image_tone = (
                payload.get("diagram_image_tone")
                if "diagram_image_tone" in payload
                else next_metadata.get("diagram_image_tone") or "auto"
            )
            if image_tone not in {"auto", "original"}:
                raise HTTPException(status_code=422, detail="diagram_image_tone must be auto or original")
            next_metadata.update(
                {
                    "diagram_tikz_source": None,
                    "diagram_svg": None,
                    "diagram_image_path": image_path,
                    "diagram_image_crop": crop if crop_was_provided else next_metadata.get("diagram_image_crop"),
                    "diagram_image_tone": image_tone,
                    "diagram_render_status": "ready" if image_path else None,
                    "diagram_error": None,
                    "diagram_needs_review": False,
                }
            )
        else:
            next_metadata.update(
                {
                    "diagram_tikz_source": None,
                    "diagram_svg": None,
                    "diagram_image_path": None,
                    "diagram_image_crop": None,
                    "diagram_image_tone": None,
                    "diagram_render_status": None,
                    "diagram_error": None,
                    "diagram_needs_review": False,
                }
            )
    try:
        updated_problem = Problem.model_validate(
            {
                **problem.model_dump(),
                "content_format": content_format,
                "problem_text": payload.get("problem_text", problem.problem_text),
                "options": options,
                "question_type": question_type,
                "source": (
                    payload.get("source") or ""
                    if "source" in payload
                    else problem.source
                ),
                "has_diagram": payload.get(
                    "diagram_detected",
                    problem.has_diagram,
                ),
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
    api.TAG_STORE.ensure(TagDimension.KNOWLEDGE, updated_problem.knowledge_points)
    api.TAG_STORE.ensure(TagDimension.ERROR, updated_problem.error_hypothesis)
    api.TAG_STORE.ensure(TagDimension.CUSTOM, list(next_metadata.get("user_tags") or []))
    task = api.TASK_STORE.update(
        task_id,
        problem=updated_problem,
        metadata=next_metadata,
        revision_count=(task.revision_count or 0) + 1,
        last_revised_at=datetime.now(timezone.utc),
        difficulty_coefficient_override=difficulty_coefficient_override,
        section_question_count=section_question_count,
    )
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
    if not task.metadata.get("diagram_tikz_source"):
        raise HTTPException(status_code=422, detail="Problem has no persisted TikZ source")
    task = api.TASK_STORE.update(
        task_id,
        metadata={
            **task.metadata,
            "diagram_svg": None,
            "diagram_render_status": "pending",
            "diagram_error": None,
            "diagram_needs_review": False,
        },
    )
    return {"task": api._task_view(task)}


@router.post("/upload")
def upload_task(payload: UploadRequest) -> dict[str, Any]:
    api = _api()
    try:
        path, detected_mime_type = api.ASSET_STORE.save_uploaded_image(
            payload.image_base64,
            payload.filename,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    metadata = payload.model_dump(exclude={"image_base64", "filename", "mime_type"})
    metadata["mime_type"] = detected_mime_type
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
            source_label = session.filename
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
            metadata["source"] = source_label
            metadata["source_page"] = payload.batch_page_index + 1 if payload.batch_page_index is not None else None
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
    api.TAG_STORE.ensure(TagDimension.KNOWLEDGE, payload.knowledge_tags)
    api.TAG_STORE.ensure(TagDimension.ERROR, payload.error_tags)
    api.TAG_STORE.ensure(TagDimension.CUSTOM, payload.user_tags)
    return {"task": api._task_view(task)}


__all__ = ["router"]
