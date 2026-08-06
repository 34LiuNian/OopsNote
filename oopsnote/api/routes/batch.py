"""Manual batch-session routes."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from oopsnote.api.errors import api_error
from oopsnote.api.schemas import (
    BatchDeleteRequest,
    BatchProcessRequest,
    BatchSessionPatchRequest,
)
from oopsnote.core import (
    BatchSessionRecord,
    BatchSessionUpdateRequest,
    StateConflict,
    TaskStatus,
)
from oopsnote.core.assets import AssetUploadTooLargeError
from oopsnote.api.services.batch_processing import (
    BatchProcessError,
    BatchProcessingContext,
    process_batch_session as run_batch_process,
)

router = APIRouter()

# DNS-only access is intentionally used for the public OopsNote origin, so the
# bounded server-side upload contract can support full scanned documents.
BATCH_SOURCE_MAX_BYTES = 500 * 1024 * 1024


def _api():
    from oopsnote.api import main

    return main.request_api()


def _validate_batch_source_length(request: Request) -> None:
    """Reject known oversized requests before creating any temporary asset."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > BATCH_SOURCE_MAX_BYTES:
                raise api_error(
                    413,
                    code="batch_source_too_large",
                    message=f"Batch source exceeds the {BATCH_SOURCE_MAX_BYTES} byte limit",
                    scope="batch",
                )
        except ValueError as error:
            raise api_error(
                400,
                code="request_invalid",
                message="Invalid Content-Length",
                scope="batch",
            ) from error

@router.get("/batch-sessions")
def list_batch_sessions() -> dict[str, list[dict[str, Any]]]:
    api = _api()
    return {
        "items": [
            api._batch_session_view(api._sync_batch_session_tasks(record))
            for record in api.BATCH_SESSION_STORE.list_all()
        ]
    }


@router.get("/batch-sessions/upload-limits")
def get_batch_upload_limits() -> dict[str, int]:
    return {"source_max_bytes": BATCH_SOURCE_MAX_BYTES}


@router.get("/batch-sessions/{file_hash}")
def get_batch_session(file_hash: str) -> dict[str, Any]:
    api = _api()
    try:
        record = api.BATCH_SESSION_STORE.get(file_hash)
    except KeyError:
        raise api_error(
            404,
            code="batch_session_not_found",
            message="批量扫描会话不存在",
            scope="batch",
            details={"file_hash": file_hash},
        )
    return {
        "session": api._batch_session_view(api._sync_batch_session_tasks(record))
    }


@router.get("/batch-sessions/{file_hash}/source")
def get_batch_source(file_hash: str) -> FileResponse:
    api = _api()
    try:
        record = api.BATCH_SESSION_STORE.get(file_hash)
    except KeyError:
        raise api_error(
            404,
            code="batch_session_not_found",
            message="批量扫描会话不存在",
            scope="batch",
            details={"file_hash": file_hash},
        )
    if not api.ASSET_STORE.is_available(record.asset_path, record.file_hash):
        raise api_error(
            404,
            code="batch_source_unavailable",
            message="原始批量文件不可用，请重新导入相同内容的文件以恢复批量扫描",
            scope="batch",
            details={"file_hash": file_hash},
        )
    return FileResponse(
        api.ASSET_STORE.resolve(record.asset_path),
        media_type=record.mime_type,
        filename=record.filename,
    )


@router.put("/batch-sessions/{file_hash}/source")
async def upload_batch_source(file_hash: str, request: Request) -> dict[str, Any]:
    api = _api()
    filename = unquote(
        request.headers.get("x-oopsnote-filename", "batch-upload.bin")
    )
    mime_type = request.headers.get("content-type", "application/octet-stream")
    try:
        page_count = max(0, int(request.headers.get("x-oopsnote-page-count", "0")))
    except ValueError as exc:
        raise api_error(
            400,
            code="batch_page_count_invalid",
            message="批量文件页数无效",
            scope="batch",
            details={"file_hash": file_hash},
        ) from exc
    _validate_batch_source_length(request)
    try:
        record = api.BATCH_SESSION_STORE.get(file_hash)
    except KeyError:
        try:
            asset_path = await api.ASSET_STORE.save_stream(
                request.stream(),
                filename,
                stable_name=f"batch-{file_hash}",
                expected_sha256=file_hash,
                max_bytes=BATCH_SOURCE_MAX_BYTES,
            )
        except AssetUploadTooLargeError as error:
            raise api_error(413, code="batch_source_too_large", message=str(error), scope="batch") from error
        except ValueError as error:
            raise api_error(400, code="batch_source_invalid", message=str(error), scope="batch") from error
        record = api.BATCH_SESSION_STORE.create(
            BatchSessionRecord(
                file_hash=file_hash,
                filename=filename,
                mime_type=mime_type,
                asset_path=asset_path,
                page_count=page_count,
            )
        )
    else:
        # A deleted source must be recoverable without discarding the mutable
        # session or its task links. The stream is hash-verified and written
        # atomically before the session reference is refreshed.
        if not api.ASSET_STORE.is_available(record.asset_path, record.file_hash):
            try:
                asset_path = await api.ASSET_STORE.save_stream(
                    request.stream(),
                    filename,
                    stable_name=f"batch-{file_hash}",
                    expected_sha256=file_hash,
                    max_bytes=BATCH_SOURCE_MAX_BYTES,
                )
            except AssetUploadTooLargeError as error:
                raise api_error(413, code="batch_source_too_large", message=str(error), scope="batch") from error
            except ValueError as error:
                raise api_error(400, code="batch_source_invalid", message=str(error), scope="batch") from error
            record = api.BATCH_SESSION_STORE.update(
                file_hash,
                BatchSessionUpdateRequest(
                    asset_path=asset_path,
                    filename=filename,
                    mime_type=mime_type,
                    page_count=page_count,
                ),
                expected_revision=record.revision,
            )
    return {"session": api._batch_session_view(record)}


@router.patch("/batch-sessions/{file_hash}")
def update_batch_session(
    file_hash: str,
    payload: BatchSessionPatchRequest,
) -> dict[str, Any]:
    api = _api()
    try:
        expected_revision = payload.expected_revision
        record = api.BATCH_SESSION_STORE.update(
            file_hash,
            BatchSessionUpdateRequest.model_validate(
                payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
            ),
            expected_revision=expected_revision,
        )
    except KeyError:
        raise api_error(404, code="batch_session_not_found", message="批量扫描会话不存在", scope="batch")
    except StateConflict as error:
        raise api_error(
            409,
            code="batch_revision_conflict",
            message=str(error),
            retryable=True,
            scope="batch",
            details={"file_hash": file_hash},
        ) from error
    except ValueError as error:
        raise api_error(422, code="request_invalid", message=str(error), scope="batch") from error
    if payload.filename is not None:
        api._sync_batch_source_references(file_hash, record.filename)
    return {"session": api._batch_session_view(record)}


@router.post("/batch-sessions/{file_hash}/process")
def process_batch_session(
    file_hash: str,
    payload: BatchProcessRequest,
) -> dict[str, Any]:
    """Render, create, bind, and enqueue every persisted pending segment."""
    api = _api()
    # Batch admission uses the same process-wide backend as individual tasks;
    # callers cannot split one batch across runtime backends.
    selected_backend = api._configured_backend()
    runner = api._runner_for(selected_backend)
    try:
        return run_batch_process(
            BatchProcessingContext(
                task_store=api.TASK_STORE,
                asset_store=api.ASSET_STORE,
                session_store=api.BATCH_SESSION_STORE,
                job_store=api.BATCH_PROCESS_JOB_STORE,
                session_view=api._batch_session_view,
                task_state_view=api._sync_batch_session_tasks,
            ),
            file_hash,
            selected_backend,
            runner,
            expected_revision=payload.expected_revision,
        )
    except BatchProcessError as error:
        raise api_error(
            error.status_code,
            code=error.code,
            message=str(error),
            retryable=error.retryable,
            scope="batch",
            details={"file_hash": file_hash},
        ) from error


@router.post("/batch-sessions/{file_hash}/segments/{segment_id}/retry")
def retry_batch_segment(
    file_hash: str,
    segment_id: str,
    payload: BatchProcessRequest,
) -> dict[str, Any]:
    """Retry one batch selection, recreating its task if its link is stale."""
    api = _api()
    selected_backend = api._configured_backend()
    runner = api._runner_for(selected_backend)
    try:
        return run_batch_process(
            BatchProcessingContext(
                task_store=api.TASK_STORE,
                asset_store=api.ASSET_STORE,
                session_store=api.BATCH_SESSION_STORE,
                job_store=api.BATCH_PROCESS_JOB_STORE,
                session_view=api._batch_session_view,
                task_state_view=api._sync_batch_session_tasks,
            ),
            file_hash,
            selected_backend,
            runner,
            expected_revision=payload.expected_revision,
            retry_segment_id=segment_id,
        )
    except BatchProcessError as error:
        raise api_error(
            error.status_code,
            code=error.code,
            message=str(error),
            retryable=error.retryable,
            scope="batch",
            details={"file_hash": file_hash, "segment_id": segment_id},
        ) from error


def _batch_task_ids(api: Any, record: BatchSessionRecord) -> set[str]:
    task_ids = {
        segment.task_id for segment in record.segments if segment.task_id
    }
    for task in api.TASK_STORE.list_all():
        snapshot = task.metadata.get("selection_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("source_file_hash") == record.file_hash:
            task_ids.add(task.id)
    return task_ids


@router.delete("/batch-sessions/{file_hash}")
def delete_batch_session(
    file_hash: str,
    payload: BatchDeleteRequest | None = None,
) -> dict[str, Any]:
    api = _api()
    if payload is None:
        try:
            record = api.BATCH_SESSION_STORE.delete(file_hash)
        except KeyError:
            raise HTTPException(status_code=404, detail="Batch session not found")
        return {
            "deleted": True,
            "file_hash": record.file_hash,
            "preserved_task_ids": [
                segment.task_id for segment in record.segments if segment.task_id
            ],
        }

    if not any((payload.source, payload.selection_records, payload.tasks)):
        raise HTTPException(status_code=422, detail="Select at least one batch component to delete")

    with api.BATCH_SESSION_STORE.session_lock(file_hash):
        try:
            record = api.BATCH_SESSION_STORE.get(file_hash)
        except KeyError:
            raise HTTPException(status_code=404, detail="Batch session not found")

        task_ids = _batch_task_ids(api, record)
        tasks = []
        for task_id in task_ids:
            try:
                tasks.append(api.TASK_STORE.get(task_id))
            except KeyError:
                continue

        if (payload.source or payload.selection_records) and any(
            segment.status == "processing" for segment in record.segments
        ):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete batch source or selection records while processing is active",
            )
        if payload.tasks and any(
            task.active_run_id
            or task.status == TaskStatus.PROCESSING
            or any(item.active_run_id for item in task.diagram_items)
            for task in tasks
        ):
            raise HTTPException(status_code=409, detail="Cancel active tasks before deleting them")

        if payload.source:
            try:
                api.ASSET_STORE.delete(record.asset_path)
            except FileNotFoundError:
                pass
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
        if payload.tasks:
            for task in tasks:
                api.TASK_STORE.delete(task.id)
        if payload.selection_records:
            api.BATCH_SESSION_STORE.delete(file_hash)

    return {
        "file_hash": file_hash,
        "source_deleted": payload.source,
        "selection_records_deleted": payload.selection_records,
        "tasks_deleted": len(tasks) if payload.tasks else 0,
        "preserved_task_ids": sorted(task.id for task in tasks) if not payload.tasks else [],
    }


@router.delete("/batch-sessions/{file_hash}/source")
def delete_batch_source(file_hash: str) -> dict[str, Any]:
    """Remove only the source document and retain the editable session/history."""
    api = _api()
    with api.BATCH_SESSION_STORE.session_lock(file_hash):
        try:
            record = api.BATCH_SESSION_STORE.get(file_hash)
        except KeyError:
            raise HTTPException(status_code=404, detail="Batch session not found")
        if any(segment.status == "processing" for segment in record.segments):
            raise HTTPException(status_code=409, detail="Cannot remove the source while batch processing is active")
        try:
            api.ASSET_STORE.delete(record.asset_path)
        except FileNotFoundError:
            pass
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "deleted": True,
        "file_hash": record.file_hash,
        "source_available": False,
        "preserved_task_ids": [segment.task_id for segment in record.segments if segment.task_id],
    }


__all__ = ["router"]
