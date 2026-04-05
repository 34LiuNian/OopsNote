from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.deps import require_admin
from ..models import TaskResponse
from .deps import get_tasks_service

router = APIRouter(dependencies=[Depends(require_admin)])


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
            svc._write_stream_event(  # pylint: disable=protected-access
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
