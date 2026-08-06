"""FastAPI composition root for OopsNote's Web boundary.

Route behavior lives in ``oopsnote.api.routes``. This module owns long-lived
stores, managed runners, DTO presentation helpers, and application assembly.
"""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from oopsnote.ai import HermesRunner, LangChainRunner, PiRpcBackend, PiRpcRunner
from oopsnote.ai.langchain_tools import McpHttpToolClient
from oopsnote.ai.providers import ProviderClientFactory, ProviderProfile
from oopsnote.ai.secrets import SecretStore, secret_store_from_environment
from oopsnote.api.auth import AuthenticationError, auth_config_from_env, authenticate_request
from oopsnote.api.errors import category_for_error_code, error_detail, scope_for_path
from oopsnote.api.routes import ai_settings, batch, catalog, latex, papers, study, tasks
from oopsnote.api.schemas import TagInput, TagRenameInput, UploadRequest
from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH
from oopsnote.content import option_label
from oopsnote.paper import difficulty_review_reason
from oopsnote.core import (
    AssetStore,
    AppSettingsStore,
    BatchSessionRecord,
    BatchSessionStore,
    BatchProcessJobStore,
    BatchSessionUpdateRequest,
    Problem,
    PaperDraftStore,
    ProblemMergeStore,
    RunStore,
    TagStore,
    TaskRecord,
    TaskStatus,
    TaskStore,
)
from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime
from oopsnote.mcp.ocr import (
    clear_ocr_run_model_resolver,
    clear_ocr_vault,
    close_ocr_client,
    configure_ocr_run_model_resolver,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)
STORAGE_DIR = Path(os.getenv("OOPSNOTE_STORAGE_DIR", str(PROJECT_ROOT / "storage")))
_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "OOPSNOTE_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
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
BATCH_PROCESS_JOB_STORE = BatchProcessJobStore(STORAGE_DIR / "batch_jobs")
APP_SETTINGS_STORE = AppSettingsStore(STORAGE_DIR / "settings" / "app_settings.json")
RUN_STORE = RunStore(STORAGE_DIR / "runs")
PAPER_DRAFT_STORE = PaperDraftStore(STORAGE_DIR / "papers")
PROBLEM_MERGE_STORE = ProblemMergeStore(STORAGE_DIR / "settings" / "problem_merges.json")
MCP_HTTP_RUNTIME = SharedMcpHttpRuntime()
_SUPPORTED_AI_BACKENDS = frozenset({"hermes", "langchain", "pi"})
_DEFAULT_AI_BACKEND = os.getenv("OOPSNOTE_AI_BACKEND", "langchain").strip().lower()
_ENABLED_AI_BACKENDS = frozenset(
    name.strip().lower()
    for name in os.getenv("OOPSNOTE_ENABLED_AI_BACKENDS", _DEFAULT_AI_BACKEND).split(",")
    if name.strip()
)
if _DEFAULT_AI_BACKEND not in _SUPPORTED_AI_BACKENDS:
    raise RuntimeError(f"Unsupported OOPSNOTE_AI_BACKEND: {_DEFAULT_AI_BACKEND}")
if _DEFAULT_AI_BACKEND not in _ENABLED_AI_BACKENDS:
    raise RuntimeError("OOPSNOTE_AI_BACKEND must be included in OOPSNOTE_ENABLED_AI_BACKENDS")
if unsupported_backends := _ENABLED_AI_BACKENDS - _SUPPORTED_AI_BACKENDS:
    raise RuntimeError(
        f"Unsupported OOPSNOTE_ENABLED_AI_BACKENDS: {', '.join(sorted(unsupported_backends))}"
    )


def _runner_settings() -> dict[str, int]:
    return {
        "timeout_seconds": int(os.getenv("OOPSNOTE_AI_TIMEOUT_SECONDS", "600")),
        "stale_seconds": int(os.getenv("OOPSNOTE_AI_STALE_SECONDS", "900")),
    }


@lru_cache(maxsize=1)
def get_secret_store() -> SecretStore:
    """Return the process-wide platform vault selected at the composition root."""
    return secret_store_from_environment()


def _new_hermes_runner() -> HermesRunner:
    return HermesRunner(
        project_root=PROJECT_ROOT,
        task_store=TASK_STORE,
        run_store=RUN_STORE,
        **_runner_settings(),
    )


def _new_pi_runner() -> PiRpcRunner:
    return PiRpcRunner(
        backend=PiRpcBackend(
            PROJECT_ROOT,
            runtime=os.getenv("OOPSNOTE_RPC_RUNTIME", "pi-rust"),
        ),
        project_root=PROJECT_ROOT,
        task_store=TASK_STORE,
        run_store=RUN_STORE,
        max_concurrent_tasks=int(APP_SETTINGS_STORE.get().get("pi_concurrency", os.getenv(
            "OOPSNOTE_RPC_MAX_WORKERS", os.getenv("OOPSNOTE_PI_MAX_CONCURRENT_TASKS", "3")
        ))),
        **_runner_settings(),
    )


def _langchain_provider_factory() -> ProviderClientFactory:
    return ProviderClientFactory(get_secret_store())


def _langchain_tool_client() -> McpHttpToolClient:
    environment = MCP_HTTP_RUNTIME.start()
    return McpHttpToolClient(environment["OOPSNOTE_MCP_URL"], environment["OOPSNOTE_MCP_TOKEN"])


def _new_langchain_runner() -> LangChainRunner:
    return LangChainRunner(
        project_root=PROJECT_ROOT,
        task_store=TASK_STORE,
        run_store=RUN_STORE,
        settings_store=APP_SETTINGS_STORE,
        provider_factory=_langchain_provider_factory,
        tool_client_factory=_langchain_tool_client,
        asset_store=ASSET_STORE,
        max_concurrent_tasks=int(APP_SETTINGS_STORE.get().get("ai_max_concurrency", 4)),
        **_runner_settings(),
    )


def _langchain_vision_model(run_id: str) -> Any | None:
    """Resolve Vision from the immutable run strategy at the shared MCP boundary."""
    run = RUN_STORE.get(run_id)
    snapshot = run.provider_profile_snapshot
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("vision"), dict):
        return None
    profile = ProviderProfile.model_validate(snapshot["vision"])
    return _langchain_provider_factory().create_vision_ocr_model(profile)


def _build_enabled_runners(enabled: frozenset[str]) -> dict[str, Any]:
    factories = {
        "hermes": _new_hermes_runner,
        "langchain": _new_langchain_runner,
        "pi": _new_pi_runner,
    }
    return {name: factories[name]() for name in sorted(enabled)}


_RUNNERS = _build_enabled_runners(_ENABLED_AI_BACKENDS)
HERMES_RUNNER = _RUNNERS.get("hermes")
PI_RUNNER = _RUNNERS.get("pi")
LANGCHAIN_RUNNER = _RUNNERS.get("langchain")

_DEFAULT_TAG_DIMENSIONS = {
    "knowledge": {"label": "知识体系", "label_variant": "default"},
    "error": {"label": "错题归因", "label_variant": "default"},
    "meta": {"label": "来源", "label_variant": "default"},
    "custom": {"label": "自定义标签", "label_variant": "default"},
}
_saved_tag_dimensions = APP_SETTINGS_STORE.get().get("tag_dimensions")
TAG_DIMENSIONS = {
    key: (
        _saved_tag_dimensions.get(key, default)
        if isinstance(_saved_tag_dimensions, dict)
        and isinstance(_saved_tag_dimensions.get(key, default), dict)
        else default
    )
    for key, default in _DEFAULT_TAG_DIMENSIONS.items()
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
        "source_available": _batch_source_available(record),
        "page_count": record.page_count,
        "subject": record.subject,
        "notes": record.notes,
        "active_page": record.active_page,
        "crop_rect": record.crop_rect.model_dump(),
        "crop_confirmed": record.crop_confirmed,
        "column_layout": record.column_layout.model_dump(),
        "excluded_page_indices": record.excluded_page_indices,
        "segments": [segment.model_dump() for segment in record.segments],
        "submitted_selections": _batch_submitted_selection_views(record.file_hash),
        "revision": record.revision,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _batch_source_available(record: BatchSessionRecord) -> bool:
    return ASSET_STORE.is_available(record.asset_path, record.file_hash)


def _batch_submitted_selection_views(file_hash: str) -> list[dict[str, Any]]:
    """Return immutable task provenance for rendering after session edits/deletion."""
    views: list[dict[str, Any]] = []
    for task in TASK_STORE.list_all():
        snapshot = task.metadata.get("selection_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("source_file_hash") != file_hash:
            continue
        parts = snapshot.get("parts")
        if not isinstance(parts, list) or not parts:
            continue
        views.append({
            "id": str(snapshot.get("segment_id") or f"task:{task.id}"),
            "task_id": task.id,
            "question_no": snapshot.get("question_no"),
            "status": task.status.value,
            "parts": parts,
            "crop_rect": snapshot.get("crop_rect"),
            "column_layout": snapshot.get("column_layout"),
        })
    views.sort(key=lambda item: (item.get("question_no") or 0, item["task_id"]))
    return views


def _sync_batch_source_references(file_hash: str, filename: str) -> None:
    """Keep persisted task/problem source labels aligned with a renamed batch file."""
    for task in TASK_STORE.list_all():
        metadata = task.metadata
        trace = metadata.get("trace")
        if not isinstance(trace, dict) or trace.get("kind") != "batch_segment":
            continue
        if trace.get("source_file_hash") != file_hash:
            continue
        page_index = trace.get("page_index")
        source = filename
        next_trace = {**trace, "source_file_name": filename}
        next_metadata = {
            **metadata,
            "source": source,
            "source_page": page_index + 1 if isinstance(page_index, int) and page_index >= 0 else None,
            "trace": next_trace,
        }
        next_problem = task.problem
        if next_problem:
            next_problem = next_problem.model_copy(
                update={
                    "source": source,
                    "source_page": next_metadata["source_page"],
                }
            )
        if next_metadata != metadata or next_problem != task.problem:
            TASK_STORE.update(task.id, metadata=next_metadata, problem=next_problem)


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
    current = {**trace, "batch_session_available": available}
    if file_hash and available:
        try:
            current["source_file_name"] = BATCH_SESSION_STORE.get(file_hash).filename
        except KeyError:
            pass
    return current


def _problem_source(task: TaskRecord, problem: Problem) -> Optional[str]:
    metadata = task.metadata
    trace = metadata.get("trace")
    if isinstance(trace, dict) and trace.get("kind") == "batch_segment":
        file_hash = trace.get("source_file_hash")
        trace_filename = trace.get("source_file_name")
        if file_hash:
            try:
                session = BATCH_SESSION_STORE.get(file_hash)
            except KeyError:
                pass
            else:
                return session.filename
        if isinstance(trace_filename, str) and trace_filename.strip():
            return trace_filename.strip()
    return problem.source or metadata.get("source")


def _sync_batch_session_tasks(record: BatchSessionRecord) -> BatchSessionRecord:
    """Project current task state into a read-only batch-session view."""
    return _sync_batch_session_tasks_locked(record)


def _sync_batch_session_tasks_locked(record: BatchSessionRecord) -> BatchSessionRecord:
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
            elif task.status == TaskStatus.PROCESSING:
                task_status = "processing"
            else:
                # Admission can fail before the managed lifecycle creates a
                # run (for example, when a provider credential is missing).
                # A pending task is not processing in that state; preserve
                # the session's durable failure evidence instead of showing a
                # phantom in-flight task.
                task_status = "pending"
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
                status = "failed" if task_status == "pending" and segment.status == "failed" else task_status
                review_reason = None
                review_previous_status = None
            next_segment = segment.model_copy(
                update={
                    "status": status,
                    "review_reason": review_reason,
                    "review_previous_status": review_previous_status,
                    "problem_ids": [task.problem.id] if task.problem else [],
                    "error": (
                        task.last_error
                        if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}
                        else segment.error if status == "failed" else None
                    ),
                }
            )
        changed = changed or next_segment != segment
        segments.append(next_segment)
    if not changed:
        return record
    return record.model_copy(update={"segments": segments})


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
    difficulty_reason = difficulty_review_reason(task)
    diagram = task.diagram_items[0] if task.diagram_items else None
    selected = (
        next(
            (candidate for candidate in diagram.candidates if candidate.id == diagram.selected_candidate_id),
            None,
        )
        if diagram else None
    )
    diagram_kind = (
        "tikz" if diagram and diagram.status.value == "ready_tikz" else
        "image" if diagram and diagram.status.value == "ready_image" else
        None
    )
    diagram_svg = None
    if selected and selected.svg_path:
        try:
            diagram_svg = ASSET_STORE.resolve(selected.svg_path).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeError, ValueError):
            diagram_svg = None
    diagram_items = [
        {
            **item.model_dump(mode="json"),
            "error_category": (
                category_for_error_code(item.last_error_code, needs_review=item.needs_review).value
                if item.last_error_code or item.needs_review else None
            ),
        }
        for item in task.diagram_items
    ]
    return {
        "problem_id": problem.id,
        "question_no": task.effective_question_no(),
        "chapter": task.effective_chapter(),
        "question_type": problem.question_type.value,
        "source": _problem_source(task, problem),
        "content_format": problem.content_format.value,
        "problem_text": problem.problem_text,
        "options": [
            {"key": option_label(index), "text": option}
            for index, option in enumerate(problem.options)
        ],
        "difficulty": problem.difficulty,
        "difficulty_coefficient_override": task.difficulty_coefficient_override,
        "section_question_count": task.section_question_count,
        "difficulty_needs_review": difficulty_reason is not None,
        "difficulty_review_reason": difficulty_reason,
        "has_diagram": problem.has_diagram,
        "diagram_detected": bool(diagram or problem.has_diagram),
        "diagram_kind": diagram_kind,
        "diagram_tikz_source": selected.tikz_source if selected and diagram_kind == "tikz" else None,
        "diagram_svg": diagram_svg if diagram_kind == "tikz" else None,
        "diagram_svg_path": selected.svg_path if selected and diagram_kind == "tikz" else None,
        "diagram_image_path": diagram.fallback_image_path if diagram else None,
        "diagram_image_crop": diagram.source_region.model_dump() if diagram and diagram.source_region else None,
        "diagram_image_tone": diagram.image_tone if diagram else "auto",
        "diagram_position": diagram.position if diagram else "right",
        "diagram_scale_percent": diagram.scale_percent if diagram else 100,
        "diagram_render_status": diagram.status.value if diagram else None,
        "diagram_error": diagram.last_error if diagram else None,
        "diagram_error_category": (
            category_for_error_code(diagram.last_error_code, needs_review=diagram.needs_review).value
            if diagram and (diagram.last_error_code or diagram.needs_review) else None
        ),
        "diagram_needs_review": diagram.needs_review if diagram else False,
        "diagram_items": diagram_items,
        "knowledge_tags": problem.knowledge_points,
        "error_tags": problem.error_hypothesis,
        "user_tags": metadata.get("user_tags", []),
        "trace": _trace_view(metadata.get("trace")),
    }


def _run_view(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "attempt": run.attempt,
        "purpose": run.purpose.value,
        "priority": run.priority,
        "diagram_item_id": run.diagram_item_id,
        "diagram_mode": run.diagram_mode.value if run.diagram_mode else None,
        "diagram_max_candidates": run.diagram_max_candidates,
        "diagram_step": run.diagram_step.value if run.diagram_step else None,
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
        "peak_memory_bytes": run.peak_memory_bytes,
        "retry_count": run.retry_count,
        "retryable": run.retryable,
        "prompt_version": run.prompt_version,
        "queued_at": run.queued_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "heartbeat_at": run.heartbeat_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "error_code": run.error_code,
        "error_category": (
            category_for_error_code(run.error_code).value if run.error_code else None
        ),
        "error_message": run.error_message,
        "stages": [stage.model_dump(mode="json") for stage in run.stage_runs],
        "evidence": {
            "artifacts": [
                {
                    "stage": artifact.stage.value,
                    "kind": artifact.kind,
                    "recorded_at": artifact.recorded_at.isoformat(),
                }
                for artifact in run.artifacts
            ],
            "validation_error_count": len(run.validation_errors),
        },
    }


def _task_view(record: TaskRecord) -> dict[str, Any]:
    problem = record.problem
    run = RUN_STORE.latest_for_task(record.id)
    diagram_runs = [
        candidate for candidate in RUN_STORE.list_for_task(record.id)
        if candidate.purpose.value == "diagram"
    ]
    merged_into = None
    if problem:
        canonical_problem_id = PROBLEM_MERGE_STORE.canonical_for(problem.id)
        if canonical_problem_id != problem.id:
            target = next(
                (task for task in TASK_STORE.list_all() if task.problem and task.problem.id == canonical_problem_id),
                None,
            )
            if target:
                merged_into = {"task_id": target.id, "problem_id": canonical_problem_id}
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": record.stage.value if record.stage else None,
        "stage_message": record.stage_message or record.last_error,
        "active_run_id": record.active_run_id,
        "error_category": (
            category_for_error_code(record.last_error_code).value
            if record.last_error_code else None
        ),
        "diagram_needs_review": any(item.needs_review for item in record.diagram_items),
        "revision_count": record.revision_count,
        "last_revised_at": (
            record.last_revised_at.isoformat() if record.last_revised_at else None
        ),
        "run": _run_view(run) if run else None,
        "diagram_runs": [
            _run_view(candidate)
            for candidate in sorted(diagram_runs, key=lambda item: item.queued_at, reverse=True)
        ],
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
        "merged_into": merged_into,
    }


def _task_summary(record: TaskRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": record.stage.value if record.stage else None,
        "stage_message": record.stage_message or record.last_error,
        "active_run_id": record.active_run_id,
        "error_category": (
            category_for_error_code(record.last_error_code).value
            if record.last_error_code else None
        ),
        "diagram_needs_review": any(item.needs_review for item in record.diagram_items),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "subject": record.subject,
        "question_no": record.effective_question_no(),
        "asset": _asset_view(record),
    }


def _problem_summary(task: TaskRecord, problem: Problem) -> dict[str, Any]:
    metadata = task.metadata
    view = _problem_view(task, problem)
    return {
        **view,
        "task_id": task.id,
        "subject": problem.subject or task.subject,
        "knowledge_points": problem.knowledge_points,
        "created_at": problem.created_at.isoformat(),
    }


def _runner_for(backend: str):
    if backend not in _SUPPORTED_AI_BACKENDS:
        raise HTTPException(status_code=422, detail="backend must be pi, langchain, or hermes")
    try:
        return _RUNNERS[backend]
    except KeyError:
        raise HTTPException(status_code=422, detail=f"backend {backend} is not enabled")


def _configured_backend() -> str:
    """Return the process-wide backend selected by deployment configuration."""
    return _DEFAULT_AI_BACKEND


def _run_managed(task_id: str, run_id: str, backend: str) -> None:
    _runner_for(backend).run(task_id, run_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ai_settings.retire_legacy_provider_configuration()
    runners = list(_RUNNERS.values())
    for runner in runners:
        runner.recover_orphaned_running()
        runner.recover_stale()
    if PI_RUNNER is not None:
        PI_RUNNER.set_child_environment(MCP_HTTP_RUNTIME.start())
    for runner in runners:
        runner.start_dispatcher()
        runner.recover_queued()
    configure_ocr_run_model_resolver(_langchain_vision_model)
    try:
        yield
    finally:
        for runner in runners:
            runner.shutdown_dispatcher()
        if PI_RUNNER is not None:
            PI_RUNNER.shutdown()
        MCP_HTTP_RUNTIME.shutdown()
        clear_ocr_vault()
        clear_ocr_run_model_resolver()
        close_ocr_client()


app = FastAPI(title="OopsNote", version="0.3.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    task_id = request.path_params.get("task_id")
    return JSONResponse(
        status_code=422,
        content={
            "detail": error_detail(
                code="request_invalid",
                message="请求参数无效",
                scope=scope_for_path(request.url.path),
                task_id=task_id if isinstance(task_id, str) else None,
                details={"issues": jsonable_encoder(error.errors())},
            )
        },
    )


@app.exception_handler(Exception)
async def internal_server_error(request: Request, error: Exception) -> JSONResponse:
    logger.error(
        "Unhandled API error for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(error), error, error.__traceback__),
    )
    task_id = request.path_params.get("task_id")
    return JSONResponse(
        status_code=500,
        content={
            "detail": error_detail(
                code="internal_error",
                message="服务内部错误",
                scope=scope_for_path(request.url.path),
                task_id=task_id if isinstance(task_id, str) else None,
            )
        },
    )


@app.middleware("http")
async def oidc_authentication(request, call_next):
    config = auth_config_from_env()
    if (
        not config.enabled
        or request.url.path == "/health"
    ):
        return await call_next(request)
    try:
        request.state.auth = authenticate_request(request, config)
    except AuthenticationError as error:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=STORAGE_DIR / "assets"), name="assets")


@app.get("/health")
def health() -> dict[str, Any]:
    auth_config = auth_config_from_env()
    runner = _RUNNERS[_DEFAULT_AI_BACKEND]
    ai_status = {
        "backend": runner.backend_name,
        **runner.dispatcher_status(),
    }
    if PI_RUNNER is not None and runner is PI_RUNNER:
        ai_status.update({
            "runtime": PI_RUNNER.backend.runtime_kind,
            "runtime_version": PI_RUNNER.backend.runtime_version,
        })
    return {
        "status": "ok",
        "version": "0.3.0",
        "auth": {
            "mode": auth_config.mode if (auth_config.enabled or auth_config.local) else "disabled",
        },
        "ai": ai_status,
    }


app.include_router(tasks.router)
app.include_router(batch.router)
app.include_router(ai_settings.router)
app.include_router(catalog.router)
app.include_router(latex.router)
app.include_router(papers.router)
app.include_router(study.router)


__all__ = [
    "ASSET_STORE",
    "APP_SETTINGS_STORE",
    "BATCH_SESSION_STORE",
    "HERMES_RUNNER",
    "PI_RUNNER",
    "LANGCHAIN_RUNNER",
    "PAPER_DRAFT_STORE",
    "PROBLEM_MERGE_STORE",
    "RUN_STORE",
    "STORAGE_DIR",
    "TAG_STORE",
    "TASK_STORE",
    "TagInput",
    "TagRenameInput",
    "UploadRequest",
    "app",
]
