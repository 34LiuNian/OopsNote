from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import (
    OverrideProblemRequest,
    RetagRequest,
    TaskCreateRequest,
    TaskResponse,
    TasksResponse,
    TaskStatus,
    UploadRequest,
)
from .deps import get_tasks_service

router = APIRouter()


def _svc(request: Request):
    """Resolve task service from shared API dependencies."""
    return get_tasks_service(request)


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    request: Request, payload: TaskCreateRequest, auto_process: bool = True
) -> TaskResponse:
    """Create a new task.

    Args:
        request: HTTP request
        payload: Task creation payload
        auto_process: Whether to start processing immediately

    Returns:
        Created task response
    """
    task = _svc(request).create_task(payload, auto_process=auto_process)
    return TaskResponse(task=task)


@router.get("/tasks", response_model=TasksResponse)
def list_tasks(
    request: Request,
    status: TaskStatus | None = None,
    active_only: bool = True,  # Default to active-only to show in-progress tasks
    subject: str | None = None,
) -> TasksResponse:
    return _svc(request).list_tasks(
        status=status, active_only=active_only, subject=subject
    )


@router.post("/upload", response_model=TaskResponse, status_code=201)
def upload_task(
    request: Request, upload: UploadRequest, auto_process: bool = True
) -> TaskResponse:
    task = _svc(request).upload_task(upload, auto_process=auto_process)
    return TaskResponse(task=task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(request: Request, task_id: str) -> TaskResponse:
    task = _svc(request).get_task(task_id)
    return TaskResponse(task=task)


@router.post("/tasks/{task_id}/process", response_model=TaskResponse)
def process_task(
    request: Request, task_id: str, background: bool = False
) -> TaskResponse:
    task = _svc(request).process_task(task_id, background=background)
    return TaskResponse(task=task)


@router.post("/tasks/{task_id}/simulate", response_model=TaskResponse)
def simulate_processing(
    request: Request, task_id: str, background: bool = True
) -> TaskResponse:
    """Simulate task processing with fake progress events for testing."""
    import threading
    import time

    svc = _svc(request)

    # Mark as processing
    svc.repository.patch_task(task_id, stage="simulating", stage_message="模拟处理中")

    def send_fake_progress():
        """Send fake progress events to test SSE."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.info("Starting fake progress for task %s", task_id)
            logger.info("svc type: %s", type(svc))
            logger.info("svc has event_bus: %s", hasattr(svc, "event_bus"))
            logger.info("svc.event_bus: %s", getattr(svc, "event_bus", "NOT_FOUND"))

            stages = [
                ("starting", "开始处理"),
                ("ocr", "OCR 提取中..."),
                ("solver", "解题中..."),
                ("tagger", "打标中..."),
                ("done", "处理完成"),
            ]

            for stage, message in stages:
                time.sleep(8)  # Simulate work - 20 seconds per stage
                # Write progress to stream file
                svc._write_stream_event(  # pylint: disable=protected-access
                    task_id, "progress", {"stage": stage, "message": message}
                )

            logger.info("Fake progress completed for task %s", task_id)

        except Exception as e:
            logger.error(
                "Error in send_fake_progress for task %s: %s", task_id, e, exc_info=True
            )
            raise

        # Mark as completed
        svc.repository.patch_task(task_id, stage="done", stage_message="模拟完成")

    if background:
        # Start in background thread with better error handling
        def run_with_error_handling():
            try:
                send_fake_progress()
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.error(
                    "Error in background simulate thread for task %s: %s",
                    task_id,
                    e,
                    exc_info=True,
                )

        thread = threading.Thread(
            target=run_with_error_handling,
            name=f"simulate-{task_id}",
            daemon=True,
        )
        thread.start()
    else:
        send_fake_progress()

    return TaskResponse(task=svc.get_task(task_id))


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
def retry_task(
    request: Request,
    task_id: str,
    background: bool = True,
) -> TaskResponse:
    task = _svc(request).retry_task(task_id, background=background)
    return TaskResponse(task=task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(request: Request, task_id: str) -> TaskResponse:
    task = _svc(request).cancel_task(task_id)
    return TaskResponse(task=task)


@router.post("/tasks/{task_id}/problems/{problem_id}/ocr", response_model=TaskResponse)
def rerun_ocr(request: Request, task_id: str, problem_id: str) -> TaskResponse:
    task = _svc(request).rerun_ocr(task_id, problem_id)
    return TaskResponse(task=task)


@router.post(
    "/tasks/{task_id}/problems/{problem_id}/retag", response_model=TaskResponse
)
def retag_problem(
    request: Request, task_id: str, problem_id: str, payload: RetagRequest
) -> TaskResponse:
    task = _svc(request).retag_problem(task_id, problem_id, force=payload.force)
    return TaskResponse(task=task)


@router.patch(
    "/tasks/{task_id}/problems/{problem_id}/override", response_model=TaskResponse
)
def override_problem(
    request: Request, task_id: str, problem_id: str, override: OverrideProblemRequest
) -> TaskResponse:
    task = _svc(request).override_problem(task_id, problem_id, override)
    return TaskResponse(task=task)


@router.delete("/tasks/{task_id}", response_model=TaskResponse)
def delete_task(request: Request, task_id: str) -> TaskResponse:
    task = _svc(request).delete_task(task_id)
    return TaskResponse(task=task)


@router.delete("/tasks/{task_id}/problems/{problem_id}", response_model=TaskResponse)
def delete_problem(request: Request, task_id: str, problem_id: str) -> TaskResponse:
    task = _svc(request).delete_problem(task_id, problem_id)
    return TaskResponse(task=task)


@router.post(
    "/tasks/{task_id}/problems/{problem_id}/retry", response_model=TaskResponse
)
def retry_problem(request: Request, task_id: str, problem_id: str) -> TaskResponse:
    task = _svc(request).retry_problem(task_id, problem_id)
    return TaskResponse(task=task)
