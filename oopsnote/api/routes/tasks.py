"""Task, run, upload, and problem mutation routes."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from oopsnote.ai.diagram_renderer import TikzRenderClient, TikzRenderError
from oopsnote.api.errors import ApiErrorCategory, api_error
from oopsnote.api.schemas import UploadRequest
from oopsnote.core import (
    ContentFormat,
    DiagramCandidate,
    DiagramItem,
    DiagramRunMode,
    DiagramStatus,
    Problem,
    QuestionType,
    TagDimension,
    TaskCreateRequest,
    TaskStatus,
)

router = APIRouter()


class DiagramRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_candidates: int = Field(default=4, ge=1, le=8)
    instruction: str | None = Field(default=None, max_length=2000)


class DiagramCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tikz_source: str = Field(min_length=1, max_length=80_000)


def _diagram_runner(*, task_id: str | None = None, item_id: str | None = None):
    api = _api()
    try:
        return api._runner()
    except RuntimeError as error:
        raise api_error(
            503,
            code="diagram_runner_unavailable",
            message="题图重建服务当前不可用",
            category=ApiErrorCategory.MODEL_REQUEST,
            retryable=True,
            scope="diagram",
            task_id=task_id,
            diagram_item_id=item_id,
        ) from error


def _diagram_item(task: Any, item_id: str) -> DiagramItem:
    item = next((candidate for candidate in task.diagram_items if candidate.id == item_id), None)
    if item is None:
        raise api_error(
            404,
            code="diagram_item_not_found",
            message="题图项目不存在",
            category=ApiErrorCategory.REQUEST,
            scope="diagram",
            task_id=task.id,
            diagram_item_id=item_id,
        )
    return item


def _problem_edit_error(
    task_id: str,
    message: str,
    *,
    status_code: int = 422,
    field: str | None = None,
) -> HTTPException:
    return api_error(
        status_code,
        code="request_invalid",
        message=message,
        scope="problem_edit",
        task_id=task_id,
        details={"field": field} if field else None,
    )


def _api():
    # Imported lazily so main remains the composition root and tests can replace
    # its local stores/runners without rebuilding the FastAPI application.
    from oopsnote.api import main

    return main.request_api()


@router.get("/tasks")
def list_tasks(
    active_only: bool = False,
    status: TaskStatus | None = None,
    subject: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    tasks = api.TASK_STORE.list_all()
    if active_only:
        tasks = [
            task for task in tasks if task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}
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
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error


@router.post("/tasks")
def create_task(payload: TaskCreateRequest) -> dict[str, Any]:
    api = _api()
    return {"task": api._task_view(api.TASK_STORE.create(payload))}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    if (
        task.active_run_id
        or task.status == TaskStatus.PROCESSING
        or any(item.active_run_id for item in task.diagram_items)
    ):
        raise api_error(
            409,
            code="task_busy",
            message="请先取消正在运行的题目任务",
            task_id=task_id,
            scope="task",
        )
    api.TASK_STORE.delete(task_id)
    return {"success": True}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    try:
        api._runner().cancel(task_id)
    except RuntimeError as error:
        code = getattr(error, "code", "task_cancel_conflict")
        raise api_error(
            409,
            code=code,
            message="题目任务无法取消" if code == "task_cancel_conflict" else str(error),
            task_id=task_id,
            scope="task",
        ) from error
    return {"task": api._task_view(api.TASK_STORE.get(task_id))}


def _enqueue(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    runner = api._runner()
    runner.recover_stale()
    try:
        run = runner.submit(task_id)
    except RuntimeError as error:
        code = getattr(error, "code", "run_admission_failed")
        conflict = code in {"task_busy", "admission_conflict"}
        quota_rejection = code in {"concurrency_exceeded", "daily_limit_exceeded"}
        raise api_error(
            429 if quota_rejection else 409 if conflict else 503,
            code=code,
            message=(
                "题目已有正在运行的任务"
                if code == "task_busy"
                else "题目状态已变化，请刷新后重试"
                if code == "admission_conflict"
                else "题目处理任务未能排队"
            ),
            retryable=(
                code == "admission_conflict"
                or code == "concurrency_exceeded"
                or (not conflict and not quota_rejection)
            ),
            task_id=task_id,
            scope="task",
        ) from error
    return {
        "task": api._task_view(api.TASK_STORE.get(task_id)),
        "run": api._run_view(run),
    }


@router.post("/tasks/{task_id}/process")
def process_task(
    task_id: str,
) -> dict[str, Any]:
    return _enqueue(task_id)


@router.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: str,
) -> dict[str, Any]:
    return _enqueue(task_id)


@router.get("/tasks/{task_id}/runs")
def list_task_runs(task_id: str) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    try:
        api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
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
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error

    problem = task.problem
    if not problem:
        raise api_error(
            404,
            code="problem_not_found",
            message="题目内容尚未提取",
            task_id=task_id,
            scope="problem_edit",
        )
    question_type = problem.question_type
    if payload.get("question_type"):
        try:
            question_type = QuestionType(payload["question_type"])
        except ValueError as error:
            raise _problem_edit_error(task_id, "不支持的题型", field="question_type") from error
    options = payload.get("options", problem.options)
    if options and isinstance(options[0], dict):
        options = [item.get("text", "") for item in options]
    content_format = problem.content_format
    if payload.get("content_format"):
        try:
            content_format = ContentFormat(payload["content_format"])
        except ValueError as error:
            raise _problem_edit_error(
                task_id, "不支持的内容格式", field="content_format"
            ) from error
    next_metadata = dict(task.metadata)
    if "question_no" in payload:
        next_metadata["question_no"] = payload.get("question_no")
    if "chapter" in payload:
        raw_chapter = payload.get("chapter")
        if raw_chapter is not None and not isinstance(raw_chapter, str):
            raise _problem_edit_error(task_id, "章节必须是字符串或 null", field="chapter")
        chapter = raw_chapter.strip() if raw_chapter else None
        if chapter and len(chapter) > 160:
            raise _problem_edit_error(task_id, "章节不能超过 160 个字符", field="chapter")
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
            raise _problem_edit_error(
                task_id, "难度系数必须是数字或 null", field="difficulty_coefficient_override"
            )
        elif not math.isfinite(raw_override) or not 0 <= raw_override <= 1:
            raise _problem_edit_error(
                task_id, "难度系数必须在 0 到 1 之间", field="difficulty_coefficient_override"
            )
        else:
            difficulty_coefficient_override = float(raw_override)
    section_question_count = task.section_question_count
    if "section_question_count" in payload:
        raw_total = payload.get("section_question_count")
        if raw_total is None:
            section_question_count = None
        elif isinstance(raw_total, bool) or not isinstance(raw_total, int) or raw_total < 1:
            raise _problem_edit_error(
                task_id, "小节题数必须是正整数或 null", field="section_question_count"
            )
        else:
            section_question_count = raw_total
    diagram_items = list(task.diagram_items)
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
        diagram_detected = bool(payload.get("diagram_detected", problem.has_diagram))
        current_item = diagram_items[0] if diagram_items else None
        diagram_kind = payload.get(
            "diagram_kind",
            "tikz"
            if current_item and current_item.status == DiagramStatus.READY_TIKZ
            else "image"
            if current_item and current_item.status == DiagramStatus.READY_IMAGE
            else None,
        )
        if not diagram_detected:
            diagram_kind = None
        if diagram_kind not in {None, "tikz", "image"}:
            raise _problem_edit_error(
                task_id, "题图类型必须是 tikz、image 或 null", field="diagram_kind"
            )

        diagram_position = payload.get(
            "diagram_position", current_item.position if current_item else "right"
        )
        if diagram_position not in {"left", "right"}:
            raise _problem_edit_error(
                task_id, "题图位置必须是 left 或 right", field="diagram_position"
            )

        diagram_scale = payload.get(
            "diagram_scale_percent", current_item.scale_percent if current_item else 100
        )
        if diagram_scale is not None:
            if isinstance(diagram_scale, bool) or not isinstance(diagram_scale, (int, float)):
                raise _problem_edit_error(
                    task_id, "题图缩放比例必须是数字或 null", field="diagram_scale_percent"
                )
            diagram_scale = round(diagram_scale)
            if diagram_scale < 50 or diagram_scale > 200:
                raise _problem_edit_error(
                    task_id, "题图缩放比例必须在 50 到 200 之间", field="diagram_scale_percent"
                )

        if current_item and current_item.active_run_id:
            raise api_error(
                409,
                code="diagram_run_active",
                message="请先取消正在运行的题图任务",
                scope="problem_edit",
                task_id=task_id,
                diagram_item_id=current_item.id,
            )
        if diagram_detected and current_item is None:
            current_item = DiagramItem(
                source_asset_path=task.asset_path,
                position=diagram_position,
                scale_percent=diagram_scale or 100,
            )
            diagram_items.append(current_item)
        elif current_item is not None:
            current_item = DiagramItem.model_validate(
                {
                    **current_item.model_dump(),
                    **{
                        "position": diagram_position,
                        "scale_percent": diagram_scale or 100,
                        "updated_at": datetime.now(UTC),
                    },
                }
            )
            diagram_items[0] = current_item
        if diagram_kind == "tikz":
            tikz_source = str(payload.get("diagram_tikz_source") or "").strip()
            if diagram_detected and not tikz_source:
                raise _problem_edit_error(
                    task_id, "TikZ 题图必须提供源码", field="diagram_tikz_source"
                )
            assert current_item is not None
            selected = next(
                (
                    candidate
                    for candidate in current_item.candidates
                    if candidate.id == current_item.selected_candidate_id
                ),
                None,
            )
            if selected is None or selected.tikz_source != tikz_source:
                try:
                    bundle = TikzRenderClient(api.ASSET_STORE).render(tikz_source)
                except TikzRenderError as error:
                    bundle = None
                    render_error = error
                else:
                    render_error = None
                selected = DiagramCandidate(
                    ordinal=max(
                        (candidate.ordinal for candidate in current_item.candidates), default=0
                    )
                    + 1,
                    parent_candidate_id=current_item.selected_candidate_id,
                    source_kind="human",
                    tikz_source=tikz_source,
                    svg_path=bundle.svg_path if bundle else None,
                    pdf_path=bundle.pdf_path if bundle else None,
                    png_path=bundle.png_path if bundle else None,
                    renderer_profile_version=bundle.renderer_profile_version if bundle else None,
                    decision="accept" if bundle else "revise",
                    review_reason=str(render_error) if render_error else None,
                )
                current_item = DiagramItem.model_validate(
                    {
                        **current_item.model_dump(),
                        **{
                            "candidates": [*current_item.candidates, selected],
                            "selected_candidate_id": selected.id,
                            "status": DiagramStatus.READY_TIKZ
                            if bundle
                            else DiagramStatus.NEEDS_REVIEW,
                            "needs_review": not bool(bundle),
                            "last_error": str(render_error) if render_error else None,
                            "last_error_code": render_error.code if render_error else None,
                        },
                    }
                )
                diagram_items[0] = current_item
        elif diagram_kind == "image":
            crop_was_provided = "diagram_image_crop" in payload
            crop = payload.get("diagram_image_crop") if crop_was_provided else None
            if crop_was_provided and crop is None:
                image_path = task.asset_path
            elif crop is not None:
                if not task.asset_path:
                    raise _problem_edit_error(
                        task_id, "图片题图需要题目原图", field="diagram_image_crop"
                    )
                try:
                    image_path, crop = api.ASSET_STORE.save_image_crop(task.asset_path, crop)
                except (FileNotFoundError, ValueError) as error:
                    raise _problem_edit_error(
                        task_id, str(error), field="diagram_image_crop"
                    ) from error
            else:
                image_path = (
                    payload.get("diagram_image_path")
                    or (current_item.fallback_image_path if current_item else None)
                    or task.asset_path
                )
            if diagram_detected and not image_path:
                raise _problem_edit_error(
                    task_id, "图片题图需要题目原图", field="diagram_image_path"
                )
            allowed_paths = {
                task.asset_path,
                current_item.fallback_image_path if current_item else None,
            }
            if image_path and image_path not in allowed_paths and crop is None:
                raise _problem_edit_error(
                    task_id, "题图路径必须属于当前题目", field="diagram_image_path"
                )
            image_tone = (
                payload.get("diagram_image_tone")
                if "diagram_image_tone" in payload
                else (current_item.image_tone if current_item else "auto")
            )
            if image_tone not in {"auto", "original"}:
                raise _problem_edit_error(
                    task_id, "题图色调必须是 auto 或 original", field="diagram_image_tone"
                )
            assert current_item is not None
            current_item = DiagramItem.model_validate(
                {
                    **current_item.model_dump(),
                    **{
                        "fallback_image_path": image_path,
                        "source_region": crop if crop_was_provided else current_item.source_region,
                        "image_tone": image_tone,
                        "status": DiagramStatus.READY_IMAGE,
                        "needs_review": False,
                        "last_error": None,
                        "last_error_code": None,
                    },
                }
            )
            diagram_items[0] = current_item
    try:
        updated_problem = Problem.model_validate(
            {
                **problem.model_dump(),
                "content_format": content_format,
                "problem_text": payload.get("problem_text", problem.problem_text),
                "options": options,
                "question_type": question_type,
                "source": (payload.get("source") or "" if "source" in payload else problem.source),
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
        raise _problem_edit_error(task_id, str(error)) from error
    api.TAG_STORE.ensure(TagDimension.KNOWLEDGE, updated_problem.knowledge_points)
    api.TAG_STORE.ensure(TagDimension.ERROR, updated_problem.error_hypothesis)
    api.TAG_STORE.ensure(TagDimension.CUSTOM, list(next_metadata.get("user_tags") or []))
    task = api.TASK_STORE.update(
        task_id,
        problem=updated_problem,
        metadata=next_metadata,
        diagram_items=diagram_items,
        revision_count=(task.revision_count or 0) + 1,
        last_revised_at=datetime.now(UTC),
        difficulty_coefficient_override=difficulty_coefficient_override,
        section_question_count=section_question_count,
    )
    return {"task": api._task_view(task)}


@router.post("/tasks/{task_id}/problem/diagram")
def rerender_problem_diagram(task_id: str) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="diagram"
        ) from error
    if not task.problem:
        raise api_error(
            404,
            code="problem_not_found",
            message="题目内容尚未提取",
            task_id=task_id,
            scope="diagram",
        )
    if not task.diagram_items:
        raise api_error(
            422,
            code="diagram_item_not_found",
            message="题目没有可重渲染的题图",
            task_id=task_id,
            scope="diagram",
        )
    item = task.diagram_items[0]
    if item.active_run_id:
        raise api_error(
            409,
            code="diagram_run_active",
            message="题图重建正在运行",
            task_id=task_id,
            diagram_item_id=item.id,
            scope="diagram",
        )
    candidate = next(
        (candidate for candidate in item.candidates if candidate.id == item.selected_candidate_id),
        None,
    )
    if candidate is None:
        raise api_error(
            422,
            code="tikz_source_missing",
            message="没有可重渲染的 TikZ 源码",
            task_id=task_id,
            diagram_item_id=item.id,
            scope="diagram",
        )
    try:
        bundle = TikzRenderClient(api.ASSET_STORE).render(candidate.tikz_source)
    except TikzRenderError as error:
        raise api_error(
            503 if error.retryable else 422,
            code=error.code,
            message=str(error),
            category=ApiErrorCategory.TIKZ_COMPILE,
            retryable=error.retryable,
            scope="diagram",
            task_id=task_id,
            diagram_item_id=item.id,
        ) from error
    candidates = [
        DiagramCandidate.model_validate(
            {
                **existing.model_dump(),
                **{
                    "svg_path": bundle.svg_path,
                    "pdf_path": bundle.pdf_path,
                    "png_path": bundle.png_path,
                    "renderer_profile_version": bundle.renderer_profile_version,
                },
            }
        )
        if existing.id == candidate.id
        else existing
        for existing in item.candidates
    ]
    task = api.TASK_STORE.update_diagram_item(
        task_id,
        item.id,
        candidates=candidates,
        status=DiagramStatus.READY_TIKZ,
        needs_review=False,
        last_error=None,
        last_error_code=None,
    )
    return {"task": api._task_view(task)}


@router.post("/tasks/{task_id}/diagrams/reconstruct", status_code=202)
def reconstruct_problem_diagram(task_id: str, payload: DiagramRunRequest) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    if not task.problem:
        raise api_error(
            409,
            code="question_not_ready",
            message="请先完成题目提取",
            task_id=task_id,
            scope="diagram",
        )
    if not task.asset_path:
        raise api_error(
            422,
            code="source_image_missing",
            message="题目没有可用于重建的原图",
            task_id=task_id,
            scope="diagram",
        )
    if len(task.diagram_items) > 1:
        raise api_error(
            409,
            code="request_invalid",
            message="当前题图重建接口暂只支持单个题图项目",
            task_id=task_id,
            scope="diagram",
            details={"max_items": 1},
        )
    if task.diagram_items:
        item = task.diagram_items[0]
        mode = DiagramRunMode.REBUILD if item.candidates else DiagramRunMode.AUTO
    else:
        item = DiagramItem(source_asset_path=task.asset_path)
        task = api.TASK_STORE.add_diagram_item(task_id, item)
        mode = DiagramRunMode.AUTO
    try:
        run = _diagram_runner(task_id=task_id, item_id=item.id).submit_diagram(
            task_id,
            item.id,
            mode=mode,
            instruction=payload.instruction,
            max_candidates=payload.max_candidates,
        )
    except (KeyError, RuntimeError, ValueError) as error:
        code = getattr(error, "code", "diagram_admission_failed")
        conflict = code in {"task_busy", "diagram_run_active", "admission_conflict"}
        raise api_error(
            409 if conflict else 503,
            code=code,
            message="题图重建任务无法排队" if code == "diagram_admission_failed" else str(error),
            retryable=code in {"diagram_admission_failed", "admission_conflict"},
            task_id=task_id,
            diagram_item_id=item.id,
            scope="diagram",
        ) from error
    return {"task": api._task_view(api.TASK_STORE.get(task_id)), "run": api._run_view(run)}


def _submit_diagram_mode(
    task_id: str,
    item_id: str,
    payload: DiagramRunRequest,
    mode: DiagramRunMode,
) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    _diagram_item(task, item_id)
    try:
        run = _diagram_runner(task_id=task_id, item_id=item_id).submit_diagram(
            task_id,
            item_id,
            mode=mode,
            instruction=payload.instruction,
            max_candidates=payload.max_candidates,
        )
    except (KeyError, RuntimeError, ValueError) as error:
        code = getattr(error, "code", "diagram_admission_failed")
        conflict = code in {"task_busy", "diagram_run_active", "admission_conflict"}
        raise api_error(
            409 if conflict else 503,
            code=code,
            message="题图重建任务无法排队" if code == "diagram_admission_failed" else str(error),
            retryable=code in {"diagram_admission_failed", "admission_conflict"},
            task_id=task_id,
            diagram_item_id=item_id,
            scope="diagram",
        ) from error
    return {"task": api._task_view(api.TASK_STORE.get(task_id)), "run": api._run_view(run)}


@router.post("/tasks/{task_id}/diagrams/{item_id}/continue", status_code=202)
def continue_problem_diagram(
    task_id: str, item_id: str, payload: DiagramRunRequest
) -> dict[str, Any]:
    return _submit_diagram_mode(task_id, item_id, payload, DiagramRunMode.CONTINUE)


@router.post("/tasks/{task_id}/diagrams/{item_id}/rebuild", status_code=202)
def rebuild_problem_diagram(
    task_id: str, item_id: str, payload: DiagramRunRequest
) -> dict[str, Any]:
    return _submit_diagram_mode(task_id, item_id, payload, DiagramRunMode.REBUILD)


@router.post("/tasks/{task_id}/diagrams/{item_id}/cancel")
def cancel_problem_diagram(task_id: str, item_id: str) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    _diagram_item(task, item_id)
    _diagram_runner(task_id=task_id, item_id=item_id).cancel_diagram(task_id, item_id)
    return {"task": api._task_view(api.TASK_STORE.get(task_id))}


@router.post("/tasks/{task_id}/diagrams/{item_id}/candidates/{candidate_id}/select")
def select_problem_diagram_candidate(
    task_id: str, item_id: str, candidate_id: str
) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    item = _diagram_item(task, item_id)
    if item.active_run_id:
        raise api_error(
            409,
            code="diagram_run_active",
            message="请先取消正在运行的题图任务",
            task_id=task_id,
            diagram_item_id=item_id,
            scope="diagram",
        )
    candidate = next((value for value in item.candidates if value.id == candidate_id), None)
    if candidate is None:
        raise api_error(
            404,
            code="candidate_not_found",
            message="题图版本不存在",
            task_id=task_id,
            diagram_item_id=item_id,
            scope="diagram",
            details={"candidate_id": candidate_id},
        )
    if not candidate.svg_path or not candidate.pdf_path:
        raise api_error(
            409,
            code="candidate_not_rendered",
            message="题图版本尚未完成渲染",
            task_id=task_id,
            diagram_item_id=item_id,
            scope="diagram",
            details={"candidate_id": candidate_id},
        )
    task = api.TASK_STORE.update_diagram_item(
        task_id,
        item_id,
        selected_candidate_id=candidate_id,
        status=DiagramStatus.READY_TIKZ,
        needs_review=False,
        last_error=None,
        last_error_code=None,
    )
    return {"task": api._task_view(task)}


@router.post("/tasks/{task_id}/diagrams/{item_id}/candidates")
def create_problem_diagram_candidate(
    task_id: str,
    item_id: str,
    payload: DiagramCandidateRequest,
) -> dict[str, Any]:
    api = _api()
    try:
        task = api.TASK_STORE.get(task_id)
    except KeyError as error:
        raise api_error(
            404, code="task_not_found", message="题目不存在", task_id=task_id, scope="task"
        ) from error
    item = _diagram_item(task, item_id)
    if item.active_run_id:
        raise api_error(
            409,
            code="diagram_run_active",
            message="请先取消正在运行的题图任务",
            task_id=task_id,
            diagram_item_id=item_id,
            scope="diagram",
        )
    try:
        bundle = TikzRenderClient(api.ASSET_STORE).render(payload.tikz_source)
    except TikzRenderError as error:
        raise api_error(
            503 if error.retryable else 422,
            code=error.code,
            message=str(error),
            category=ApiErrorCategory.TIKZ_COMPILE,
            retryable=error.retryable,
            scope="diagram",
            task_id=task_id,
            diagram_item_id=item.id,
        ) from error
    candidate = DiagramCandidate(
        ordinal=max((candidate.ordinal for candidate in item.candidates), default=0) + 1,
        parent_candidate_id=item.selected_candidate_id,
        source_kind="human",
        tikz_source=payload.tikz_source.strip(),
        svg_path=bundle.svg_path,
        pdf_path=bundle.pdf_path,
        png_path=bundle.png_path,
        renderer_profile_version=bundle.renderer_profile_version,
        decision="accept",
    )
    task = api.TASK_STORE.update_diagram_item(
        task_id,
        item_id,
        candidates=[*item.candidates, candidate],
        selected_candidate_id=candidate.id,
        status=DiagramStatus.READY_TIKZ,
        needs_review=False,
        last_error=None,
        last_error_code=None,
    )
    return {"task": api._task_view(task), "candidate": candidate.model_dump(mode="json")}


@router.post("/upload")
def upload_task(payload: UploadRequest) -> dict[str, Any]:
    api = _api()
    try:
        path, detected_mime_type = api.ASSET_STORE.save_uploaded_image(
            payload.image_base64,
            payload.filename,
        )
    except ValueError as error:
        raise api_error(
            422,
            code="request_invalid",
            message="上传的题目图片无效",
            scope="upload",
            details={"reason": str(error)},
        ) from error
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
            metadata["source_page"] = (
                payload.batch_page_index + 1 if payload.batch_page_index is not None else None
            )
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
