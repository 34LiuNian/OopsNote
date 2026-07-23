"""Manual batch-session routes."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request

from oopsnote.core import BatchSessionRecord, BatchSessionUpdateRequest

router = APIRouter()


def _api():
    from oopsnote.api import main

    return main


@router.get("/batch-sessions")
def list_batch_sessions() -> dict[str, list[dict[str, Any]]]:
    api = _api()
    return {
        "items": [
            api._batch_session_view(api._sync_batch_session_tasks(record))
            for record in api.BATCH_SESSION_STORE.list_all()
        ]
    }


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
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty batch source")
    if hashlib.sha256(payload).hexdigest() != file_hash:
        raise HTTPException(status_code=400, detail="File hash mismatch")
    try:
        record = api.BATCH_SESSION_STORE.get(file_hash)
    except KeyError:
        asset_path = api.ASSET_STORE.save_bytes(
            payload,
            filename,
            stable_name=f"batch-{file_hash}",
        )
        record = api.BATCH_SESSION_STORE.create(
            BatchSessionRecord(
                file_hash=file_hash,
                filename=filename,
                mime_type=mime_type,
                asset_path=asset_path,
            )
        )
    return {"session": api._batch_session_view(record)}


@router.patch("/batch-sessions/{file_hash}")
def update_batch_session(
    file_hash: str,
    payload: BatchSessionUpdateRequest,
) -> dict[str, Any]:
    api = _api()
    try:
        record = api.BATCH_SESSION_STORE.update(file_hash, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Batch session not found")
    return {"session": api._batch_session_view(record)}


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
