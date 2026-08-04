"""Manual batch-session routes."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request

from oopsnote.api.schemas import BatchProcessRequest, BatchSessionPatchRequest
from oopsnote.core import (
    BatchSessionRecord,
    BatchSessionUpdateRequest,
    StateConflict,
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

    return main


def _validate_batch_source_length(request: Request) -> None:
    """Reject known oversized requests before creating any temporary asset."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > BATCH_SOURCE_MAX_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Batch source exceeds the {BATCH_SOURCE_MAX_BYTES} byte limit",
                )
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from error

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
        raise HTTPException(status_code=404, detail="Batch session not found")
    return {
        "session": api._batch_session_view(api._sync_batch_session_tasks(record))
    }


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
        raise HTTPException(status_code=400, detail="Invalid batch page count") from exc
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
            raise HTTPException(status_code=413, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        record = api.BATCH_SESSION_STORE.create(
            BatchSessionRecord(
                file_hash=file_hash,
                filename=filename,
                mime_type=mime_type,
                asset_path=asset_path,
                page_count=page_count,
            )
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
        raise HTTPException(status_code=404, detail="Batch session not found")
    except StateConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
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
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.delete("/batch-sessions/{file_hash}")
def delete_batch_session(file_hash: str) -> dict[str, Any]:
    api = _api()
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


__all__ = ["router"]
