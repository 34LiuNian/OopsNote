"""FastAPI composition root for OopsNote's Web boundary.

Route behavior lives in ``oopsnote.api.routes``. This module owns long-lived
stores, managed runners, DTO presentation helpers, and application assembly.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from oopsnote.ai import HermesRunner, PiRpcBackend, PiRpcRunner
from oopsnote.api.routes import batch, catalog, tasks
from oopsnote.api.schemas import TagInput, TagRenameInput, UploadRequest
from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH
from oopsnote.core import (
    AssetStore,
    BatchSessionRecord,
    BatchSessionStore,
    BatchSessionUpdateRequest,
    Problem,
    RunStore,
    TagStore,
    TaskRecord,
    TaskStatus,
    TaskStore,
)
from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "storage"
TASK_STORE = TaskStore(base_dir=STORAGE_DIR)
TAG_STORE = TagStore(
    user_path=STORAGE_DIR / "settings" / "tags_user.json",
    builtin_path=KNOWLEDGE_TAGS_PATH,
    tree_path=KNOWLEDGE_TREES_PATH,
)
ASSET_STORE = AssetStore(base_dir=STORAGE_DIR / "assets")
BATCH_SESSION_STORE = BatchSessionStore(
    STORAGE_DIR / "settings" / "batch_sessions.json"
)
RUN_STORE = RunStore(STORAGE_DIR / "runs")
MCP_HTTP_RUNTIME = SharedMcpHttpRuntime()


def _runner_settings() -> dict[str, int]:
    return {
        "timeout_seconds": int(os.getenv("OOPSNOTE_AI_TIMEOUT_SECONDS", "600")),
        "stale_seconds": int(os.getenv("OOPSNOTE_AI_STALE_SECONDS", "900")),
    }


HERMES_RUNNER = HermesRunner(
    project_root=PROJECT_ROOT,
    task_store=TASK_STORE,
    run_store=RUN_STORE,
    **_runner_settings(),
)
PI_RUNNER = PiRpcRunner(
    backend=PiRpcBackend(
        PROJECT_ROOT,
        runtime=os.getenv("OOPSNOTE_RPC_RUNTIME", "pi-rust"),
    ),
    project_root=PROJECT_ROOT,
    task_store=TASK_STORE,
    run_store=RUN_STORE,
    max_concurrent_tasks=int(
        os.getenv(
            "OOPSNOTE_RPC_MAX_WORKERS",
            os.getenv("OOPSNOTE_PI_MAX_CONCURRENT_TASKS", "3"),
        )
    ),
    **_runner_settings(),
)

TAG_DIMENSIONS = {
    "knowledge": {"label": "知识体系", "label_variant": "default"},
    "error": {"label": "错题归因", "label_variant": "default"},
    "meta": {"label": "来源", "label_variant": "default"},
    "custom": {"label": "自定义标签", "label_variant": "default"},
}
BATCH_REVIEW_REASONS = {
    "unreadable",
    "incomplete",
    "multiple_questions",
    "other",
}


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
        "crop_rect": record.crop_rect.model_dump(),
        "crop_confirmed": record.crop_confirmed,
        "segments": [segment.model_dump() for segment in record.segments],
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _trace_view(trace: Any) -> Any:
    if not isinstance(trace, dict) or trace.get("kind") != "batch_segment":
        return trace
    file_hash = trace.get("source_file_hash")
    available = False
    if file_hash:
        try:
            BATCH_SESSION_STORE.get(file_hash)
        except KeyError:
            pass
        else:
            available = True
    return {**trace, "batch_session_available": available}


def _sync_batch_session_tasks(record: BatchSessionRecord) -> BatchSessionRecord:
    """Refresh task-derived segment state without losing manual crop data."""
    changed = False
    segments = []
    for segment in record.segments:
        if not segment.task_id:
            segments.append(segment)
            continue
        try:
            task = TASK_STORE.get(segment.task_id)
        except KeyError:
            next_segment = segment.model_copy(
                update={"status": "failed", "error": "关联任务不存在"}
            )
        else:
            if task.status == TaskStatus.COMPLETED:
                task_status = "completed"
            elif task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                task_status = "failed"
            else:
                task_status = "processing"
            task_review_reason = task.metadata.get("intake_review_reason")
            if task_review_reason not in BATCH_REVIEW_REASONS:
                task_review_reason = None
            if segment.status == "needs_review" and segment.review_reason and not segment.review_resolved:
                status = "needs_review"
                review_reason = segment.review_reason
                review_previous_status = segment.review_previous_status or task_status
            elif task_review_reason and not segment.review_resolved:
                status = "needs_review"
                review_reason = task_review_reason
                review_previous_status = task_status
            else:
                status = task_status
                review_reason = None
                review_previous_status = None
            next_segment = segment.model_copy(
                update={
                    "status": status,
                    "review_reason": review_reason,
                    "review_previous_status": review_previous_status,
                    "problem_ids": [task.problem.id] if task.problem else [],
                    "error": task.last_error if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED} else None,
                }
            )
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
        "content_format": problem.content_format.value,
        "problem_text": problem.problem_text,
        "options": [
            {"key": str(index + 1), "text": option}
            for index, option in enumerate(problem.options)
        ],
        "difficulty": problem.difficulty,
        "has_diagram": problem.has_diagram,
        "knowledge_tags": problem.knowledge_points,
        "error_tags": problem.error_hypothesis,
        "user_tags": metadata.get("user_tags", []),
        "trace": _trace_view(metadata.get("trace")),
    }


def _run_view(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "attempt": run.attempt,
        "status": run.status.value,
        "pid": run.pid,
        "exit_code": run.exit_code,
        "log_path": run.log_path,
        "rpc_log_path": run.rpc_log_path,
        "backend": run.backend,
        "runtime_kind": run.runtime_kind,
        "runtime_version": run.runtime_version,
        "worker_id": run.worker_id,
        "provider": run.provider,
        "model": run.model,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cache_tokens": run.cache_tokens,
        "cost": run.cost,
        "duration_ms": run.duration_ms,
        "retry_count": run.retry_count,
        "retryable": run.retryable,
        "prompt_version": run.prompt_version,
        "queued_at": run.queued_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "heartbeat_at": run.heartbeat_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "stages": [stage.model_dump(mode="json") for stage in run.stage_runs],
    }


def _task_view(record: TaskRecord) -> dict[str, Any]:
    problem = record.problem
    run = RUN_STORE.latest_for_task(record.id)
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": record.stage.value if record.stage else None,
        "stage_message": record.stage_message or record.last_error,
        "active_run_id": record.active_run_id,
        "run": _run_view(run) if run else None,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "asset": _asset_view(record),
        "payload": {"difficulty": record.metadata.get("difficulty")},
        "trace": _trace_view(record.metadata.get("trace")),
        "problem": _problem_view(record, problem) if problem else None,
        "solution": {
            "problem_id": problem.id,
            "answer": problem.answer,
            "short_answer": problem.short_answer,
            "explanation": problem.explanation,
        } if problem else None,
        "tag": {
            "problem_id": problem.id,
            "knowledge_points": problem.knowledge_points,
        } if problem else None,
    }


def _task_summary(record: TaskRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": record.stage.value if record.stage else None,
        "stage_message": record.stage_message or record.last_error,
        "active_run_id": record.active_run_id,
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
        "content_format": problem.content_format.value,
        "problem_text": problem.problem_text,
        "options": [
            {"key": str(index + 1), "text": option}
            for index, option in enumerate(problem.options)
        ],
        "difficulty": problem.difficulty,
        "has_diagram": problem.has_diagram,
        "subject": problem.subject or task.subject,
        "source": problem.source or metadata.get("source"),
        "knowledge_points": problem.knowledge_points,
        "knowledge_tags": problem.knowledge_points,
        "error_tags": problem.error_hypothesis,
        "user_tags": metadata.get("user_tags", []),
        "trace": metadata.get("trace"),
        "created_at": problem.created_at.isoformat(),
    }


def _runner_for(backend: str):
    runners = {"hermes": HERMES_RUNNER, "pi": PI_RUNNER}
    try:
        return runners[backend]
    except KeyError:
        raise HTTPException(status_code=422, detail="backend must be pi or hermes")


def _configured_backend(backend: Optional[str]) -> str:
    return backend or os.getenv("OOPSNOTE_AI_BACKEND", "pi").strip().lower()


def _run_managed(task_id: str, run_id: str, backend: str) -> None:
    _runner_for(backend).run(task_id, run_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    HERMES_RUNNER.recover_orphaned_running()
    PI_RUNNER.recover_orphaned_running()
    HERMES_RUNNER.recover_stale()
    PI_RUNNER.recover_stale()
    PI_RUNNER.set_child_environment(MCP_HTTP_RUNTIME.start())
    HERMES_RUNNER.start_dispatcher()
    PI_RUNNER.start_dispatcher()
    HERMES_RUNNER.recover_queued()
    PI_RUNNER.recover_queued()
    try:
        yield
    finally:
        HERMES_RUNNER.shutdown_dispatcher()
        PI_RUNNER.shutdown_dispatcher()
        PI_RUNNER.shutdown()
        MCP_HTTP_RUNTIME.shutdown()


app = FastAPI(title="OopsNote", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=STORAGE_DIR / "assets"), name="assets")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.3.0",
        "ai": {
            "runtime": PI_RUNNER.backend.runtime_kind,
            "runtime_version": PI_RUNNER.backend.runtime_version,
            **PI_RUNNER.dispatcher_status(),
        },
    }


app.include_router(tasks.router)
app.include_router(batch.router)
app.include_router(catalog.router)


__all__ = [
    "ASSET_STORE",
    "BATCH_SESSION_STORE",
    "HERMES_RUNNER",
    "PI_RUNNER",
    "RUN_STORE",
    "STORAGE_DIR",
    "TAG_STORE",
    "TASK_STORE",
    "TagInput",
    "TagRenameInput",
    "UploadRequest",
    "app",
]
