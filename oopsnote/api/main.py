"""REST boundary for the Web frontend.

The API owns DTO shaping.  Core models remain storage-oriented and are shared
with MCP and CLI without leaking a frontend-specific persistence format.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from oopsnote.core import (
    AssetStore,
    BatchSessionRecord,
    BatchSessionStore,
    BatchSessionUpdateRequest,
    Problem,
    QuestionType,
    Searcher,
    SearchQuery,
    TagDimension,
    TagStore,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    TaskStore,
)
from oopsnote.obsidian.syncer import ObsidianSyncer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "storage"
TASK_STORE = TaskStore(base_dir=STORAGE_DIR)
TAG_STORE = TagStore(
    user_path=STORAGE_DIR / "settings" / "tags_user.json",
    builtin_path=STORAGE_DIR / "settings" / "tags_builtin.json",
)
ASSET_STORE = AssetStore(base_dir=STORAGE_DIR / "assets")
BATCH_SESSION_STORE = BatchSessionStore(STORAGE_DIR / "settings" / "batch_sessions.json")

TAG_DIMENSIONS = {
    "knowledge": {"label": "知识体系", "label_variant": "default"},
    "error": {"label": "错题归因", "label_variant": "default"},
    "meta": {"label": "来源", "label_variant": "default"},
    "custom": {"label": "自定义标签", "label_variant": "default"},
}


class UploadRequest(BaseModel):
    subject: str = "auto"
    notes: str = ""
    question_no: Optional[str] = None
    source: Optional[str] = None
    question_type: Optional[str] = None
    difficulty: Optional[str] = None
    knowledge_tags: list[str] = Field(default_factory=list)
    error_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    image_base64: str
    filename: str
    mime_type: str = "image/png"
    batch_session_hash: Optional[str] = None
    batch_segment_id: Optional[str] = None
    batch_page_index: Optional[int] = Field(default=None, ge=0)
    batch_question_no: Optional[int] = Field(default=None, ge=1)


class TagInput(BaseModel):
    dimension: TagDimension
    value: str
    aliases: list[str] = Field(default_factory=list)
    subject: Optional[str] = None


class TagRenameInput(BaseModel):
    value: str


def _batch_session_view(record: BatchSessionRecord) -> dict[str, Any]:
    return {
        "file_hash": record.file_hash,
        "filename": record.filename,
        "mime_type": record.mime_type,
        "asset_path": record.asset_path,
        "page_count": record.page_count,
        "subject": record.subject,
        "notes": record.notes,
        "active_page": record.active_page,
        "segments": [segment.model_dump() for segment in record.segments],
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _sync_batch_session_tasks(record: BatchSessionRecord) -> BatchSessionRecord:
    """Refresh task-derived segment state without losing the manual crop data."""
    changed = False
    segments = []
    for segment in record.segments:
        if not segment.task_id:
            segments.append(segment)
            continue
        try:
            task = TASK_STORE.get(segment.task_id)
        except KeyError:
            next_segment = segment.model_copy(update={
                "status": "failed",
                "error": "关联任务不存在",
            })
        else:
            if task.status == TaskStatus.COMPLETED:
                status = "completed"
            elif task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                status = "failed"
            else:
                status = "processing"
            next_segment = segment.model_copy(update={
                "status": status,
                "problem_ids": [problem.id for problem in task.problems],
                "error": task.last_error if status == "failed" else None,
            })
        changed = changed or next_segment != segment
        segments.append(next_segment)
    if not changed:
        return record
    return BATCH_SESSION_STORE.update(
        record.file_hash,
        BatchSessionUpdateRequest(segments=segments),
    )


def _asset_view(record: TaskRecord) -> Optional[dict[str, Any]]:
    if not record.asset_path:
        return None
    filename = Path(record.asset_path).name
    path = STORAGE_DIR / record.asset_path.lstrip("/")
    return {
        "asset_id": Path(filename).stem,
        "source": "upload",
        "path": record.asset_path,
        "mime_type": record.metadata.get("mime_type"),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _problem_view(task: TaskRecord, problem: Problem) -> dict[str, Any]:
    metadata = task.metadata
    return {
        "problem_id": problem.id,
        "question_no": metadata.get("question_no"),
        "question_type": problem.question_type.value,
        "source": problem.source or metadata.get("source"),
        "problem_text": problem.problem_text,
        "options": [{"key": str(index + 1), "text": option} for index, option in enumerate(problem.options)],
        "knowledge_tags": problem.knowledge_points,
        "error_tags": problem.error_hypothesis,
        "user_tags": metadata.get("user_tags", []),
        "trace": metadata.get("trace"),
    }


def _task_view(record: TaskRecord) -> dict[str, Any]:
    problems = [_problem_view(record, problem) for problem in record.problems]
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": None,
        "stage_message": record.last_error,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "asset": _asset_view(record),
        "payload": {"difficulty": record.metadata.get("difficulty")},
        "trace": record.metadata.get("trace"),
        "problems": problems,
        "solutions": [
            {"problem_id": problem.id, "answer": problem.answer, "explanation": problem.explanation}
            for problem in record.problems
        ],
        "tags": [
            {"problem_id": problem.id, "knowledge_points": problem.knowledge_points}
            for problem in record.problems
        ],
    }


def _task_summary(record: TaskRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": None,
        "stage_message": record.last_error,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "subject": record.subject,
        "question_no": record.metadata.get("question_no"),
        "asset": _asset_view(record),
    }


def _problem_summary(task: TaskRecord, problem: Problem) -> dict[str, Any]:
    metadata = task.metadata
    return {
        "task_id": task.id,
        "problem_id": problem.id,
        "question_no": metadata.get("question_no"),
        "question_type": problem.question_type.value,
        "problem_text": problem.problem_text,
        "options": [{"key": str(index + 1), "text": option} for index, option in enumerate(problem.options)],
        "subject": problem.subject or task.subject,
        "source": problem.source or metadata.get("source"),
        "knowledge_points": problem.knowledge_points,
        "knowledge_tags": problem.knowledge_points,
        "error_tags": problem.error_hypothesis,
        "user_tags": metadata.get("user_tags", []),
        "trace": metadata.get("trace"),
        "created_at": problem.created_at.isoformat(),
    }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid ISO datetime")


def _run_hermes(task_id: str) -> None:
    """Start the documented Web-to-Hermes hand-off without coupling Core to AI."""
    try:
        task = TASK_STORE.get(task_id)
        prompt = f"处理 OopsNote 任务 {task.id}，图片资产为 {task.asset_path or '无'}。"
        subprocess.Popen(
            ["hermes", "--profile", "oopsnote", "chat", "-q", prompt, "-s", "oopsnote-orchestrator"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        TASK_STORE.mark_status(task_id, TaskStatus.FAILED, "Hermes is not installed or is not on PATH")
    except Exception as error:
        TASK_STORE.mark_status(task_id, TaskStatus.FAILED, str(error))


app = FastAPI(title="OopsNote", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=STORAGE_DIR / "assets"), name="assets")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0"}


@app.get("/tasks")
def list_tasks(
    active_only: bool = False,
    status: Optional[TaskStatus] = None,
    subject: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    tasks = TASK_STORE.list_all()
    if active_only:
        tasks = [task for task in tasks if task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}]
    if status:
        tasks = [task for task in tasks if task.status == status]
    if subject:
        tasks = [task for task in tasks if task.subject == subject]
    tasks.sort(key=lambda task: task.created_at, reverse=True)
    return {"items": [_task_summary(task) for task in tasks[:limit]]}


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    try:
        return {"task": _task_view(TASK_STORE.get(task_id))}
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks")
def create_task(payload: TaskCreateRequest) -> dict[str, Any]:
    task = TASK_STORE.create(payload)
    return {"task": _task_view(task)}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    try:
        TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    TASK_STORE.delete(task_id)
    return {"success": True}


@app.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    try:
        return {"task": _task_view(TASK_STORE.mark_status(task_id, TaskStatus.CANCELLED))}
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks/{task_id}/process")
def process_task(task_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        task = TASK_STORE.mark_status(task_id, TaskStatus.PROCESSING)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    background_tasks.add_task(_run_hermes, task_id)
    return {"task": _task_view(task)}


@app.post("/tasks/{task_id}/retry")
def retry_task(task_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        task = TASK_STORE.mark_status(task_id, TaskStatus.PROCESSING)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    background_tasks.add_task(_run_hermes, task_id)
    return {"task": _task_view(task)}


@app.patch("/tasks/{task_id}/problems/{problem_id}/override")
def override_problem(task_id: str, problem_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        task = TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")

    updated_problems: list[Problem] = []
    found = False
    for problem in task.problems:
        if problem.id != problem_id:
            updated_problems.append(problem)
            continue
        found = True
        question_type = problem.question_type
        if payload.get("question_type"):
            try:
                question_type = QuestionType(payload["question_type"])
            except ValueError:
                pass
        options = payload.get("options", problem.options)
        if options and isinstance(options[0], dict):
            options = [item.get("text", "") for item in options]
        updated_problems.append(problem.model_copy(update={
            "problem_text": payload.get("problem_text", problem.problem_text),
            "options": options,
            "question_type": question_type,
            "source": payload.get("source") or problem.source,
            "knowledge_points": payload.get("knowledge_tags", problem.knowledge_points),
            "error_hypothesis": payload.get("error_tags", problem.error_hypothesis),
        }))

    if not found:
        raise HTTPException(status_code=404, detail="Problem not found")
    task = TASK_STORE.set_problems(task_id, updated_problems)
    return {"task": _task_view(task)}


@app.delete("/tasks/{task_id}/problems/{problem_id}")
def delete_problem(task_id: str, problem_id: str) -> dict[str, Any]:
    try:
        task = TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    remaining = [problem for problem in task.problems if problem.id != problem_id]
    if len(remaining) == len(task.problems):
        raise HTTPException(status_code=404, detail="Problem not found")
    task = TASK_STORE.set_problems(task_id, remaining)
    return {"task": _task_view(task)}


@app.post("/tasks/{task_id}/problems/{problem_id}/diagram")
def rerender_problem_diagram(task_id: str, problem_id: str) -> dict[str, Any]:
    try:
        task = TASK_STORE.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    if not any(problem.id == problem_id for problem in task.problems):
        raise HTTPException(status_code=404, detail="Problem not found")
    return {"task": _task_view(task)}


@app.post("/upload")
def upload_task(payload: UploadRequest) -> dict[str, Any]:
    path = ASSET_STORE.save_base64(payload.image_base64, payload.filename)
    metadata = payload.model_dump(exclude={"image_base64", "filename", "mime_type"})
    metadata["mime_type"] = payload.mime_type
    trace: dict[str, Any] = {
        "kind": "single_image",
        "screenshot_path": path,
        "screenshot_filename": payload.filename,
    }
    if payload.batch_session_hash and payload.batch_segment_id:
        try:
            session = BATCH_SESSION_STORE.get(payload.batch_session_hash)
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
    task = TASK_STORE.create(
        TaskCreateRequest(
            subject=payload.subject,
            asset_path=path,
            tags=[*payload.knowledge_tags, *payload.error_tags, *payload.user_tags],
            metadata=metadata,
        )
    )
    TAG_STORE.ensure(TagDimension.META, [payload.source] if payload.source else [])
    TAG_STORE.ensure(TagDimension.KNOWLEDGE, payload.knowledge_tags)
    TAG_STORE.ensure(TagDimension.ERROR, payload.error_tags)
    TAG_STORE.ensure(TagDimension.CUSTOM, payload.user_tags)
    return {"task": _task_view(task)}


@app.get("/batch-sessions")
def list_batch_sessions() -> dict[str, list[dict[str, Any]]]:
    return {"items": [_batch_session_view(_sync_batch_session_tasks(record)) for record in BATCH_SESSION_STORE.list_all()]}


@app.get("/batch-sessions/{file_hash}")
def get_batch_session(file_hash: str) -> dict[str, Any]:
    try:
        return {"session": _batch_session_view(_sync_batch_session_tasks(BATCH_SESSION_STORE.get(file_hash)))}
    except KeyError:
        raise HTTPException(status_code=404, detail="Batch session not found")


@app.put("/batch-sessions/{file_hash}/source")
async def upload_batch_source(file_hash: str, request: Request) -> dict[str, Any]:
    filename = unquote(request.headers.get("x-oopsnote-filename", "batch-upload.bin"))
    mime_type = request.headers.get("content-type", "application/octet-stream")
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty batch source")
    if hashlib.sha256(payload).hexdigest() != file_hash:
        raise HTTPException(status_code=400, detail="File hash mismatch")
    try:
        record = BATCH_SESSION_STORE.get(file_hash)
    except KeyError:
        asset_path = ASSET_STORE.save_bytes(payload, filename, stable_name=f"batch-{file_hash}")
        record = BATCH_SESSION_STORE.create(
            BatchSessionRecord(
                file_hash=file_hash,
                filename=filename,
                mime_type=mime_type,
                asset_path=asset_path,
            )
        )
    return {"session": _batch_session_view(record)}


@app.patch("/batch-sessions/{file_hash}")
def update_batch_session(file_hash: str, payload: BatchSessionUpdateRequest) -> dict[str, Any]:
    try:
        record = BATCH_SESSION_STORE.update(file_hash, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Batch session not found")
    return {"session": _batch_session_view(record)}


@app.get("/problems")
def list_problems(
    subject: Optional[str] = None,
    source: Optional[list[str]] = Query(default=None),
    knowledge_tag: Optional[list[str]] = Query(default=None),
    error_tag: Optional[list[str]] = Query(default=None),
    user_tag: Optional[list[str]] = Query(default=None),
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    after = _parse_iso(created_after)
    before = _parse_iso(created_before)
    items: list[dict[str, Any]] = []
    for task in TASK_STORE.list_all():
        for problem in task.problems:
            item = _problem_summary(task, problem)
            if subject and item["subject"] != subject:
                continue
            if source and item["source"] not in source:
                continue
            if knowledge_tag and not set(knowledge_tag).issubset(item["knowledge_tags"]):
                continue
            if error_tag and not set(error_tag).issubset(item["error_tags"]):
                continue
            if user_tag and not set(user_tag).issubset(item["user_tags"]):
                continue
            created = problem.created_at
            if after and created < after:
                continue
            if before and created > before:
                continue
            items.append(item)
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items}


@app.get("/search")
def search(
    tags: Optional[str] = Query(default=None),
    subject: Optional[str] = None,
    since: Optional[str] = None,
    error_type: Optional[str] = None,
    regex: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[Problem]]:
    query = SearchQuery(
        tags=[tag.strip() for tag in tags.split(",") if tag.strip()] if tags else [],
        subject=subject,
        since=since,
        error_type=error_type,
        regex=regex,
        limit=limit,
    )
    return {"results": Searcher(TASK_STORE.list_all()).search(query)}


@app.get("/tags")
def list_tags(
    dimension: Optional[TagDimension] = None,
    query: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    return {"items": [item.model_dump(mode="json") for item in TAG_STORE.search(dimension, query, limit)]}


@app.post("/tags")
def create_tag(payload: TagInput) -> dict[str, list[dict[str, Any]]]:
    TAG_STORE.upsert(payload.dimension, payload.value, payload.aliases, payload.subject)
    return list_tags(dimension=payload.dimension, query=payload.value)


@app.delete("/tags/{tag_id}")
def delete_tag(tag_id: str) -> dict[str, Any]:
    if not TAG_STORE.delete(tag_id):
        raise HTTPException(status_code=404, detail="User tag not found")
    return {"ok": True, "tag_id": tag_id}


@app.put("/tags/{tag_id}")
def rename_tag(tag_id: str, payload: TagRenameInput) -> dict[str, list[dict[str, Any]]]:
    existing = TAG_STORE.get_by_id(tag_id)
    if not existing or existing.source != "user":
        raise HTTPException(status_code=404, detail="User tag not found")
    value = payload.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Tag value is required")
    if value != existing.value:
        TAG_STORE.delete(tag_id)
        TAG_STORE.upsert(existing.dimension, value, existing.aliases, existing.subject)
    return list_tags(dimension=existing.dimension, query=value)


@app.post("/tags/{source_id}/merge")
def merge_tags(source_id: str, payload: dict[str, str]) -> dict[str, Any]:
    source = TAG_STORE.get_by_id(source_id)
    target = TAG_STORE.get_by_id(payload.get("target_id", ""))
    if not source or source.source != "user" or not target or source.dimension != target.dimension:
        raise HTTPException(status_code=404, detail="Compatible source and target tags are required")
    TAG_STORE.delete(source_id)
    TAG_STORE.upsert(target.dimension, target.value, [*target.aliases, source.value, *source.aliases], target.subject)
    return {"ok": True, "tasks_modified": 0, "fields_modified": 0}


@app.get("/tags/dimensions")
@app.get("/settings/tag-dimensions")
def get_tag_dimensions() -> dict[str, Any]:
    return {"dimensions": TAG_DIMENSIONS}


@app.put("/settings/tag-dimensions")
def update_tag_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
    dimensions = payload.get("dimensions")
    if isinstance(dimensions, dict):
        for key, value in dimensions.items():
            if key in TAG_DIMENSIONS and isinstance(value, dict):
                TAG_DIMENSIONS[key] = value
    return {"dimensions": TAG_DIMENSIONS}


@app.post("/sync")
def sync(subject: Optional[str] = None) -> dict[str, str]:
    syncer = ObsidianSyncer(task_store=TASK_STORE, tag_store=TAG_STORE)
    report = syncer.sync_for_subject(subject) if subject else syncer.sync()
    return {"message": str(report)}
