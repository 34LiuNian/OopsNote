from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.deps import require_admin
from ..models import (
    DebugBatchCreateResponse,
    DebugBatchDetailResponse,
    DebugBatchTaskItem,
    DebugMultiPageUploadRequest,
    TaskResponse,
)
from .deps import get_tasks_service

router = APIRouter(dependencies=[Depends(require_admin)])


def _ensure_demo_enabled() -> None:
    if os.getenv("APP_ENABLE_MULTIPAGE_DEMO_API", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/debug/tasks/{task_id}/simulate", response_model=TaskResponse)
def simulate_processing(
    request: Request, task_id: str, background: bool = True
) -> TaskResponse:
    """仅用于调试：模拟任务进度事件。"""
    if os.getenv("APP_ENABLE_SIMULATE_TASK_API", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")

    svc = get_tasks_service(request)

    # 先将任务状态置为“模拟处理中”，便于前端调试流程。
    svc.repository.patch_task(task_id, stage="simulating", stage_message="模拟处理中")

    def send_fake_progress() -> None:
        logger = logging.getLogger(__name__)
        stages = [
            ("starting", "开始处理"),
            ("ocr", "OCR 提取中..."),
            ("solver", "解题中..."),
            ("tagger", "打标中..."),
            ("done", "处理完成"),
        ]

        for stage, message in stages:
            time.sleep(8)
            svc.emit_stream_event(
                task_id, "progress", {"stage": stage, "message": message}
            )

        logger.info("Fake progress completed for task %s", task_id)
        svc.repository.patch_task(task_id, stage="done", stage_message="模拟完成")

    if background:
        thread = threading.Thread(
            target=send_fake_progress,
            name=f"simulate-{task_id}",
            daemon=True,
        )
        thread.start()
    else:
        send_fake_progress()

    return TaskResponse(task=svc.get_task(task_id))


@router.post(
    "/debug/multipage/upload",
    response_model=DebugBatchCreateResponse,
    status_code=201,
)
def upload_multipage_demo(
    request: Request,
    payload: DebugMultiPageUploadRequest,
    auto_process: bool = True,
) -> DebugBatchCreateResponse:
    """独立 demo：上传多张整页图片并自动分割建任务。"""
    _ensure_demo_enabled()
    svc = get_tasks_service(request)
    batch_id = svc.run_debug_multipage_batch(payload, auto_process=auto_process)
    return DebugBatchCreateResponse(batch_id=batch_id)


@router.get(
    "/debug/multipage/batches/{batch_id}",
    response_model=DebugBatchDetailResponse,
)
def get_multipage_demo_batch(
    request: Request,
    batch_id: str,
) -> DebugBatchDetailResponse:
    """查询 demo 批次进度与子任务状态。"""
    _ensure_demo_enabled()
    svc = get_tasks_service(request)
    data = svc.get_debug_multipage_batch(batch_id)
    return DebugBatchDetailResponse(
        batch_id=str(data.get("batch_id") or batch_id),
        status=str(data.get("status") or "processing"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        total_images=int(data.get("total_images") or 0),
        total_regions=int(data.get("total_regions") or 0),
        total_tasks=int(data.get("total_tasks") or 0),
        completed_tasks=int(data.get("completed_tasks") or 0),
        failed_tasks=int(data.get("failed_tasks") or 0),
        cancelled_tasks=int(data.get("cancelled_tasks") or 0),
        tasks=[DebugBatchTaskItem(**item) for item in (data.get("tasks") or [])],
        warnings=[str(x) for x in (data.get("warnings") or [])],
    )
