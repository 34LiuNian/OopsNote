"""FastAPI composition root for OopsNote's Web boundary.

Route behavior lives in ``oopsnote.api.routes``. This module owns long-lived
stores, managed runners, DTO presentation helpers, and application assembly.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from oopsnote.ai import LangChainRunner
from oopsnote.ai.diagram_renderer import legacy_svg_canvas_em
from oopsnote.ai.langchain_tools import McpHttpToolClient
from oopsnote.ai.providers import ProviderClientFactory, ProviderProfile
from oopsnote.ai.secrets import SecretStore, secret_store_from_environment
from oopsnote.api.auth import (
    AuthenticationError,
    auth_config_from_env,
    authenticate_internal_request,
    authorize_local_request,
    internal_identity_config_from_env,
)
from oopsnote.api.context import (
    RequestContext,
    activate_request_context,
    current_request_context,
    reset_request_context,
)
from oopsnote.api.errors import (
    ApiErrorCategory,
    category_for_error_code,
    error_detail,
    public_error_code,
    public_error_message,
    scope_for_path,
)
from oopsnote.api.routes import (
    account,
    admin,
    ai_settings,
    batch,
    catalog,
    latex,
    papers,
    study,
    tasks,
)
from oopsnote.api.schemas import TagInput, TagRenameInput, UploadRequest
from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH
from oopsnote.content import option_label
from oopsnote.control import ControlDatabase, WorkspaceRegistry
from oopsnote.core import (
    AppSettingsStore,
    AssetStore,
    BatchProcessJobStore,
    BatchSessionRecord,
    BatchSessionStore,
    DiagramStatus,
    PaperDraftStore,
    Problem,
    ProblemMergeStore,
    RunStore,
    TagStore,
    TaskRecord,
    TaskStatus,
    TaskStore,
    WorkspaceId,
    WorkspaceStoreFactory,
    WorkspaceStores,
)
from oopsnote.mcp.context import current_capability
from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime
from oopsnote.mcp.ocr import (
    clear_ocr_results,
    clear_ocr_run_model_resolver,
    configure_ocr_run_model_resolver,
)
from oopsnote.paper import difficulty_review_reason

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
BATCH_SESSION_STORE = BatchSessionStore(STORAGE_DIR / "settings" / "batch_sessions.json")
BATCH_PROCESS_JOB_STORE = BatchProcessJobStore(STORAGE_DIR / "batch_jobs")
APP_SETTINGS_STORE = AppSettingsStore(STORAGE_DIR / "settings" / "app_settings.json")
RUN_STORE = RunStore(STORAGE_DIR / "runs")
PAPER_DRAFT_STORE = PaperDraftStore(STORAGE_DIR / "papers")
PROBLEM_MERGE_STORE = ProblemMergeStore(STORAGE_DIR / "settings" / "problem_merges.json")
CONTROL_DATABASE = ControlDatabase(STORAGE_DIR / "control" / "app.sqlite")
WORKSPACE_REGISTRY = WorkspaceRegistry(CONTROL_DATABASE, STORAGE_DIR)
WORKSPACE_STORE_FACTORY = WorkspaceStoreFactory()


def _active_stores():
    context = current_request_context()
    if context is None:
        return None
    return context.stores


def request_api():
    """Return a route facade whose user-owned stores follow the request context."""
    context = current_request_context()
    module = sys.modules[__name__]
    if context is None:
        return module
    stores = context.stores

    class ScopedApi:
        TASK_STORE = stores.task_store
        TAG_STORE = stores.tag_store
        ASSET_STORE = stores.asset_store
        BATCH_SESSION_STORE = stores.batch_session_store
        BATCH_PROCESS_JOB_STORE = stores.batch_process_job_store
        PAPER_DRAFT_STORE = stores.paper_draft_store
        PROBLEM_MERGE_STORE = stores.problem_merge_store
        RUN_STORE = stores.run_store
        OBSIDIAN_VAULT_ROOT = context.workspace.root / "obsidian-vault"

        def __getattr__(self, name: str):
            return getattr(module, name)

    return ScopedApi()


MCP_HTTP_RUNTIME = SharedMcpHttpRuntime()


def _runner_settings() -> dict[str, int]:
    return {
        "timeout_seconds": int(os.getenv("OOPSNOTE_AI_TIMEOUT_SECONDS", "600")),
        "stale_seconds": int(os.getenv("OOPSNOTE_AI_STALE_SECONDS", "900")),
    }


@lru_cache(maxsize=1)
def get_secret_store() -> SecretStore:
    """Return the process-wide platform vault selected at the composition root."""
    return secret_store_from_environment()


def _langchain_provider_factory() -> ProviderClientFactory:
    return ProviderClientFactory(get_secret_store())


def _langchain_tool_client(
    stores: WorkspaceStores | None = None,
    workspace_id: WorkspaceId | None = None,
) -> McpHttpToolClient:
    environment = MCP_HTTP_RUNTIME.start()
    if stores is not None and workspace_id is not None:
        environment = MCP_HTTP_RUNTIME.environment_for(workspace_id, stores)
    return McpHttpToolClient(environment["OOPSNOTE_MCP_URL"], environment["OOPSNOTE_MCP_TOKEN"])


def _new_langchain_runner(
    stores: WorkspaceStores | None = None,
    workspace_id: WorkspaceId | None = None,
) -> LangChainRunner:
    return LangChainRunner(
        project_root=PROJECT_ROOT,
        task_store=stores.task_store if stores else TASK_STORE,
        run_store=stores.run_store if stores else RUN_STORE,
        settings_store=APP_SETTINGS_STORE,
        provider_factory=_langchain_provider_factory,
        tool_client_factory=lambda: _langchain_tool_client(stores, workspace_id),
        asset_store=stores.asset_store if stores else ASSET_STORE,
        max_concurrent_tasks=int(APP_SETTINGS_STORE.get().get("ai_max_concurrency", 4)),
        **_runner_settings(),
    )


def _langchain_vision_model(run_id: str) -> Any | None:
    """Resolve Vision from the immutable run strategy at the shared MCP boundary."""
    capability = current_capability()
    run_store = capability.stores.run_store if capability is not None else RUN_STORE
    run = run_store.get(run_id)
    snapshot = run.provider_profile_snapshot
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("vision"), dict):
        return None
    profile = ProviderProfile.model_validate(snapshot["vision"])
    return _langchain_provider_factory().create_vision_ocr_model(profile)


_RUNNERS = {"langchain": _new_langchain_runner()}
LANGCHAIN_RUNNER = _RUNNERS["langchain"]


class WorkspaceRunnerPool:
    """Own one durable LangChain dispatcher per workspace."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runners: dict[WorkspaceId, Any] = {}

    def get(self, workspace_id: WorkspaceId, stores: WorkspaceStores):
        key = WorkspaceId.parse(workspace_id)
        with self._lock:
            existing = self._runners.get(key)
            if existing is not None:
                return existing
            runner = _new_langchain_runner(stores, key)
            reconcile = getattr(stores.run_store, "reconcile_control_runs", None)
            if callable(reconcile):
                reconcile()
            runner.recover_orphaned_running()
            runner.recover_stale()
            runner.start_dispatcher()
            runner.recover_queued()
            self._runners[key] = runner
            return runner

    def shutdown(self) -> None:
        with self._lock:
            runners = list(self._runners.values())
            self._runners.clear()
        for runner in runners:
            runner.shutdown_dispatcher()


WORKSPACE_RUNNER_POOL = WorkspaceRunnerPool()

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


@dataclass(frozen=True, slots=True)
class _BatchTaskSnapshot:
    by_id: dict[str, TaskRecord]
    by_source_file_hash: dict[str, tuple[TaskRecord, ...]]


def _batch_task_snapshot() -> _BatchTaskSnapshot:
    stores = _active_stores()
    task_store = stores.task_store if stores else TASK_STORE
    tasks = task_store.list_all()
    by_source_file_hash: dict[str, list[TaskRecord]] = {}
    for task in tasks:
        selection = task.metadata.get("selection_snapshot")
        if not isinstance(selection, dict):
            continue
        file_hash = selection.get("source_file_hash")
        if isinstance(file_hash, str) and file_hash:
            by_source_file_hash.setdefault(file_hash, []).append(task)
    return _BatchTaskSnapshot(
        by_id={task.id: task for task in tasks},
        by_source_file_hash={
            file_hash: tuple(matching_tasks)
            for file_hash, matching_tasks in by_source_file_hash.items()
        },
    )


def _batch_session_views(records: Iterable[BatchSessionRecord]) -> list[dict[str, Any]]:
    records = list(records)
    if not records:
        return []
    task_snapshot = _batch_task_snapshot()
    return [
        _batch_session_view_from_snapshot(
            _sync_batch_session_tasks_locked(record, tasks_by_id=task_snapshot.by_id),
            task_snapshot,
        )
        for record in records
    ]


def _batch_session_view(record: BatchSessionRecord) -> dict[str, Any]:
    return _batch_session_views([record])[0]


def _batch_session_view_from_snapshot(
    record: BatchSessionRecord,
    task_snapshot: _BatchTaskSnapshot,
) -> dict[str, Any]:
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
        "submitted_selections": _batch_submitted_selection_views(
            record.file_hash,
            task_snapshot,
        ),
        "revision": record.revision,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _batch_source_available(record: BatchSessionRecord) -> bool:
    """Report source presence; source-consuming boundaries verify its digest."""
    stores = _active_stores()
    asset_store = stores.asset_store if stores else ASSET_STORE
    return asset_store.exists(record.asset_path)


def _batch_submitted_selection_views(
    file_hash: str,
    task_snapshot: _BatchTaskSnapshot,
) -> list[dict[str, Any]]:
    """Return immutable task provenance for rendering after session edits/deletion."""
    views: list[dict[str, Any]] = []
    for task in task_snapshot.by_source_file_hash.get(file_hash, ()):
        snapshot = task.metadata.get("selection_snapshot")
        if not isinstance(snapshot, dict):
            continue
        parts = snapshot.get("parts")
        if not isinstance(parts, list) or not parts:
            continue
        views.append(
            {
                "id": str(snapshot.get("segment_id") or f"task:{task.id}"),
                "task_id": task.id,
                "question_no": snapshot.get("question_no"),
                "status": task.status.value,
                "parts": parts,
                "crop_rect": snapshot.get("crop_rect"),
                "column_layout": snapshot.get("column_layout"),
            }
        )
    views.sort(key=lambda item: (item.get("question_no") or 0, item["task_id"]))
    return views


def _sync_batch_source_references(file_hash: str, filename: str) -> None:
    """Keep persisted task/problem source labels aligned with a renamed batch file."""
    stores = _active_stores()
    task_store = stores.task_store if stores else TASK_STORE
    for task in task_store.list_all():
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
            "source_page": page_index + 1
            if isinstance(page_index, int) and page_index >= 0
            else None,
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
            task_store.update(task.id, metadata=next_metadata, problem=next_problem)


def _trace_view(trace: Any) -> Any:
    if not isinstance(trace, dict) or trace.get("kind") != "batch_segment":
        return trace
    file_hash = trace.get("source_file_hash")
    available = False
    if file_hash:
        try:
            stores = _active_stores()
            batch_session_store = stores.batch_session_store if stores else BATCH_SESSION_STORE
            batch_session_store.get(file_hash)
        except KeyError:
            pass
        else:
            available = True
    current = {**trace, "batch_session_available": available}
    if file_hash and available:
        with suppress(KeyError):
            current["source_file_name"] = batch_session_store.get(file_hash).filename
    return current


def _problem_source(task: TaskRecord, problem: Problem) -> str | None:
    metadata = task.metadata
    trace = metadata.get("trace")
    if isinstance(trace, dict) and trace.get("kind") == "batch_segment":
        file_hash = trace.get("source_file_hash")
        trace_filename = trace.get("source_file_name")
        if file_hash:
            try:
                stores = _active_stores()
                batch_session_store = stores.batch_session_store if stores else BATCH_SESSION_STORE
                session = batch_session_store.get(file_hash)
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


def _sync_batch_session_tasks_locked(
    record: BatchSessionRecord,
    *,
    tasks_by_id: Mapping[str, TaskRecord] | None = None,
) -> BatchSessionRecord:
    changed = False
    segments = []
    stores = _active_stores()
    task_store = stores.task_store if stores else TASK_STORE
    for segment in record.segments:
        if not segment.task_id:
            segments.append(segment)
            continue
        if tasks_by_id is None:
            try:
                task = task_store.get(segment.task_id)
            except KeyError:
                task = None
        else:
            task = tasks_by_id.get(segment.task_id)
        if task is None:
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
            if (
                segment.status == "needs_review"
                and segment.review_reason
                and not segment.review_resolved
            ):
                status = "needs_review"
                review_reason = segment.review_reason
                review_previous_status = segment.review_previous_status or task_status
            elif task_review_reason and not segment.review_resolved:
                status = "needs_review"
                review_reason = task_review_reason
                review_previous_status = task_status
            else:
                status = (
                    "failed"
                    if task_status == "pending" and segment.status == "failed"
                    else task_status
                )
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
                        else segment.error
                        if status == "failed"
                        else None
                    ),
                }
            )
        changed = changed or next_segment != segment
        segments.append(next_segment)
    if not changed:
        return record
    return record.model_copy(update={"segments": segments})


def _asset_view(record: TaskRecord) -> dict[str, Any] | None:
    if not record.asset_path:
        return None
    filename = Path(record.asset_path).name
    stores = _active_stores()
    asset_root = stores.asset_store.base_dir if stores else ASSET_STORE.base_dir
    path = asset_root / Path(record.asset_path).name
    return {
        "asset_id": Path(filename).stem,
        "source": "upload",
        "path": record.asset_path,
        "mime_type": record.metadata.get("mime_type"),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _diagram_requires_human_review(item: Any) -> bool:
    if not item.last_error_code and not item.needs_review:
        return False
    return (
        category_for_error_code(
            item.last_error_code,
            needs_review=item.needs_review,
        )
        == ApiErrorCategory.HUMAN_REVIEW
    )


def _problem_view(task: TaskRecord, problem: Problem) -> dict[str, Any]:
    stores = _active_stores()
    asset_store = stores.asset_store if stores else ASSET_STORE
    metadata = task.metadata
    difficulty_reason = difficulty_review_reason(task)
    diagram = task.diagram_items[0] if task.diagram_items else None
    diagram_enabled = bool(diagram.enabled) if diagram else bool(problem.has_diagram)
    selected = (
        next(
            (
                candidate
                for candidate in diagram.candidates
                if candidate.id == diagram.selected_candidate_id
            ),
            None,
        )
        if diagram
        else None
    )
    diagram_kind = (
        "tikz"
        if diagram
        and diagram.enabled
        and diagram.status.value != "ready_image"
        and selected is not None
        else "image"
        if diagram and diagram.enabled and diagram.status.value == "ready_image"
        else None
    )
    diagram_svg = None
    if selected and selected.svg_path:
        try:
            diagram_svg = asset_store.resolve(selected.svg_path).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeError, ValueError):
            diagram_svg = None

    diagram_base_font_size_pt = selected.base_font_size_pt if selected else None
    diagram_canvas_width_em = selected.canvas_width_em if selected else None
    diagram_canvas_height_em = selected.canvas_height_em if selected else None
    if (
        diagram_kind == "tikz"
        and selected
        and diagram_svg
        and (
            diagram_base_font_size_pt is None
            or diagram_canvas_width_em is None
            or diagram_canvas_height_em is None
        )
    ):
        legacy_metrics = legacy_svg_canvas_em(diagram_svg)
        if legacy_metrics is not None:
            diagram_base_font_size_pt = 10.0
            diagram_canvas_width_em, diagram_canvas_height_em = legacy_metrics

    def diagram_category(item: Any) -> ApiErrorCategory | None:
        if item is None:
            return None
        if not item.last_error_code and not item.needs_review:
            return None
        return category_for_error_code(
            public_error_code(item.last_error_code, item.last_error),
            needs_review=item.needs_review,
        )

    def diagram_requires_review(item: Any) -> bool:
        return _diagram_requires_human_review(item)

    diagram_items = []
    for item in task.diagram_items:
        category = diagram_category(item)
        item_view = item.model_dump(mode="json")
        # Older runs persisted every technical failure as NEEDS_REVIEW. Derive
        # the public state from the authoritative error category until those
        # records are naturally rewritten by a retry or manual action.
        if item_view["status"] == DiagramStatus.NEEDS_REVIEW.value and not diagram_requires_review(
            item
        ):
            item_view["status"] = DiagramStatus.FAILED.value
        item_view["needs_review"] = diagram_requires_review(item)
        item_view["error_category"] = category.value if category else None
        item_view["last_error_code"] = public_error_code(item.last_error_code, item.last_error)
        item_view["last_error"] = public_error_message(item.last_error_code, item.last_error)
        diagram_items.append(item_view)
    selected_diagram_category = diagram_category(diagram)
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
        "diagram_detected": diagram_enabled,
        "diagram_enabled": diagram_enabled,
        "diagram_kind": diagram_kind,
        "diagram_tikz_source": selected.tikz_source
        if selected and diagram_kind == "tikz"
        else None,
        "diagram_svg": diagram_svg if diagram_kind == "tikz" else None,
        "diagram_svg_path": (selected.svg_path if selected and diagram_kind == "tikz" else None),
        "diagram_image_path": diagram.fallback_image_path if diagram else None,
        "diagram_image_tone": diagram.image_tone if diagram else "auto",
        "diagram_placement": (
            diagram.placement.model_dump(mode="json")
            if diagram
            else {"kind": "side", "side": "right"}
        ),
        "diagram_scale_adjustment_percent": (diagram.scale_adjustment_percent if diagram else 100),
        "diagram_base_font_size_pt": diagram_base_font_size_pt,
        "diagram_canvas_width_em": diagram_canvas_width_em,
        "diagram_canvas_height_em": diagram_canvas_height_em,
        "diagram_render_status": (
            DiagramStatus.FAILED.value
            if diagram
            and diagram.status == DiagramStatus.NEEDS_REVIEW
            and not diagram_requires_review(diagram)
            else diagram.status.value
            if diagram
            else None
        ),
        "diagram_error": (
            public_error_message(diagram.last_error_code, diagram.last_error) if diagram else None
        ),
        "diagram_error_category": (
            selected_diagram_category.value if selected_diagram_category else None
        ),
        "diagram_needs_review": diagram_requires_review(diagram) if diagram else False,
        "diagram_items": diagram_items,
        "knowledge_tags": problem.knowledge_points,
        "error_tags": problem.error_hypothesis,
        "user_tags": metadata.get("user_tags", []),
        "trace": _trace_view(metadata.get("trace")),
    }


def _run_view(run: Any) -> dict[str, Any]:
    error_code = public_error_code(run.error_code, run.error_message)
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
        "backend": run.backend,
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
        "error_code": error_code,
        "error_category": (category_for_error_code(error_code).value if error_code else None),
        "error_message": public_error_message(run.error_code, run.error_message),
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


def _task_stage_message(record: TaskRecord, run: Any | None = None) -> str | None:
    """Expose terminal failure evidence instead of a stale lifecycle label."""

    if record.status == TaskStatus.FAILED:
        message = record.last_error or (run.error_message if run else None) or record.stage_message
        return public_error_message(record.last_error_code, message)
    return record.stage_message or record.last_error


def _task_view(record: TaskRecord) -> dict[str, Any]:
    stores = _active_stores()
    task_store = stores.task_store if stores else TASK_STORE
    run_store = stores.run_store if stores else RUN_STORE
    merge_store = stores.problem_merge_store if stores else PROBLEM_MERGE_STORE
    problem = record.problem
    run = run_store.latest_for_task(record.id)
    diagram_runs = [
        candidate
        for candidate in run_store.list_for_task(record.id)
        if candidate.purpose.value == "diagram"
    ]
    merged_into = None
    if problem:
        canonical_problem_id = merge_store.canonical_for(problem.id)
        if canonical_problem_id != problem.id:
            target = next(
                (
                    task
                    for task in task_store.list_all()
                    if task.problem and task.problem.id == canonical_problem_id
                ),
                None,
            )
            if target:
                merged_into = {"task_id": target.id, "problem_id": canonical_problem_id}
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": record.stage.value if record.stage else None,
        "stage_message": _task_stage_message(record, run),
        "active_run_id": record.active_run_id,
        "error_category": (
            category_for_error_code(
                public_error_code(record.last_error_code, record.last_error)
            ).value
            if public_error_code(record.last_error_code, record.last_error)
            else None
        ),
        "diagram_needs_review": any(
            _diagram_requires_human_review(item) for item in record.diagram_items
        ),
        "revision_count": record.revision_count,
        "last_revised_at": (record.last_revised_at.isoformat() if record.last_revised_at else None),
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
        }
        if problem
        else None,
        "tag": {
            "problem_id": problem.id,
            "knowledge_points": problem.knowledge_points,
        }
        if problem
        else None,
        "merged_into": merged_into,
    }


def _task_summary(record: TaskRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status.value,
        "stage": record.stage.value if record.stage else None,
        "stage_message": _task_stage_message(record),
        "active_run_id": record.active_run_id,
        "error_category": (
            category_for_error_code(
                public_error_code(record.last_error_code, record.last_error)
            ).value
            if public_error_code(record.last_error_code, record.last_error)
            else None
        ),
        "diagram_needs_review": any(
            _diagram_requires_human_review(item) for item in record.diagram_items
        ),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "subject": record.subject,
        "question_no": record.effective_question_no(),
        "asset": _asset_view(record),
    }


def _problem_summary(task: TaskRecord, problem: Problem) -> dict[str, Any]:
    view = _problem_view(task, problem)
    return {
        **view,
        "task_id": task.id,
        "subject": problem.subject or task.subject,
        "knowledge_points": problem.knowledge_points,
        "created_at": problem.created_at.isoformat(),
    }


def _runner():
    """Return the only AI runner, scoped to the active workspace when present."""
    context = current_request_context()
    if context is not None:
        return WORKSPACE_RUNNER_POOL.get(context.workspace.workspace_id, context.stores)
    return LANGCHAIN_RUNNER


def _configured_backend() -> str:
    """Return the only supported AI backend."""
    return "langchain"


@asynccontextmanager
async def lifespan(_: FastAPI):
    auth_config = auth_config_from_env()
    if auth_config.better_auth:
        internal_identity_config_from_env()
    runners = [] if auth_config.better_auth else list(_RUNNERS.values())
    for runner in runners:
        runner.recover_orphaned_running()
        runner.recover_stale()
    for runner in runners:
        runner.start_dispatcher()
        runner.recover_queued()
    configure_ocr_run_model_resolver(_langchain_vision_model)
    try:
        yield
    finally:
        for runner in runners:
            runner.shutdown_dispatcher()
        WORKSPACE_RUNNER_POOL.shutdown()
        MCP_HTTP_RUNTIME.shutdown()
        clear_ocr_run_model_resolver()
        clear_ocr_results()


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
async def authentication(request, call_next):
    config = auth_config_from_env()
    if request.url.path == "/health":
        return await call_next(request)
    context_token = None
    try:
        if config.local:
            authorize_local_request(request)
        else:
            principal = authenticate_internal_request(
                request,
                internal_identity_config_from_env(),
            )
            workspace = WORKSPACE_REGISTRY.get_or_create(principal)
            request.state.principal = principal
            request.state.workspace_context = workspace
            request.state.workspace_stores = WORKSPACE_STORE_FACTORY.for_context(workspace)
            request_context = RequestContext(
                principal=principal,
                workspace=workspace,
                stores=request.state.workspace_stores,
            )
            request.state.oopsnote_context = request_context
            context_token = activate_request_context(request_context)
    except AuthenticationError as error:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    try:
        return await call_next(request)
    finally:
        if context_token is not None:
            reset_request_context(context_token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/assets/{asset_name}")
def get_asset(asset_name: str):
    """Serve one authenticated asset from the active workspace only."""
    if Path(asset_name).name != asset_name:
        raise HTTPException(status_code=404, detail="Asset not found")
    stores = _active_stores()
    asset_root = (stores.asset_store.base_dir if stores else ASSET_STORE.base_dir).resolve()
    asset_path = (asset_root / asset_name).resolve()
    if asset_path.parent != asset_root or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)


@app.get("/health")
def health() -> dict[str, Any]:
    auth_config = auth_config_from_env()
    runner = LANGCHAIN_RUNNER
    ai_status = {
        "backend": runner.backend_name,
        **runner.dispatcher_status(),
    }
    return {
        "status": "ok",
        "version": "0.3.0",
        "auth": {
            "mode": (
                auth_config.mode if (auth_config.local or auth_config.better_auth) else "disabled"
            ),
        },
        "ai": ai_status,
    }


app.include_router(tasks.router)
app.include_router(account.router)
app.include_router(admin.router)
app.include_router(admin.internal_router)
app.include_router(batch.router)
app.include_router(ai_settings.router)
app.include_router(catalog.router)
app.include_router(latex.router)
app.include_router(papers.router)
app.include_router(study.router)


__all__ = [
    "APP_SETTINGS_STORE",
    "ASSET_STORE",
    "BATCH_SESSION_STORE",
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
