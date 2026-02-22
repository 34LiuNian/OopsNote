from __future__ import annotations

import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..models import (
    OverrideProblemRequest,
    RetagRequest,
    TaskCreateRequest,
    TaskResponse,
    TasksResponse,
    TaskStatus,
    UploadRequest,
)
from .deps import get_tasks_service, get_sse_service

router = APIRouter()


def _svc(request: Request):
    """Resolve task service from shared API dependencies."""
    return get_tasks_service(request)


def _sse_svc(request: Request):
    """Resolve SSE service from shared API dependencies."""
    return get_sse_service(request)


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    request: Request, payload: TaskCreateRequest, auto_process: bool = True
) -> TaskResponse:
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


@router.get("/tasks/{task_id}/events")
async def task_events(request: Request, task_id: str):
    """Subscribe to real-time task events (SSE)."""
    # CORS headers for SSE - these complement the global CORSMiddleware
    # We need to explicitly set them here because SSE responses need special handling
    origin = request.headers.get("origin", "")
    
    return StreamingResponse(
        _sse_svc(request).subscribe_task_events(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # Disable compression for SSE
            "Content-Encoding": "identity",
            # Explicit CORS headers for SSE
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "Content-Type, Accept",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
        },
    )


@router.get("/tasks/{task_id}/stream")
def get_task_stream(request: Request, task_id: str, max_chars: int = 200000):
    """Fetch historical stream content."""
    text = _svc(request).get_task_stream(task_id, max_chars=max_chars)
    return {"task_id": task_id, "text": text}


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
            logger.info(f"Starting fake progress for task {task_id}")
            logger.info(f"svc type: {type(svc)}")
            logger.info(f"svc has event_bus: {hasattr(svc, 'event_bus')}")
            logger.info(f"svc.event_bus: {getattr(svc, 'event_bus', 'NOT_FOUND')}")
            
            stages = [
                ("starting", "开始处理"),
                ("ocr", "OCR 提取中..."),
                ("solver", "解题中..."),
                ("tagger", "打标中..."),
                ("done", "处理完成"),
            ]
            
            for stage, message in stages:
                time.sleep(8)  # Simulate work - 20 seconds per stage
                # Use event bus if available, otherwise use legacy method
                if hasattr(svc, 'event_bus') and svc.event_bus:
                    logger.info(f"Publishing event via event bus: {stage} - {message}")
                    svc.event_bus.publish(task_id, "progress", {"stage": stage, "message": message})
                else:
                    logger.warning("No event bus available, using legacy broadcast")
                    # Fallback to legacy broadcast (should not happen in new architecture)
                    svc._legacy_broadcast(task_id, "progress", {"stage": stage, "message": message})
            
            time.sleep(0.3)
            if hasattr(svc, 'event_bus') and svc.event_bus:
                logger.info("Finishing broadcast via event bus")
                svc.event_bus.finish_broadcast(task_id)
            else:
                logger.warning("No event bus available, using legacy finish")
                svc._legacy_finish_broadcast(task_id)
                
            logger.info(f"Fake progress completed for task {task_id}")
            
        except Exception as e:
            logger.error(f"Error in send_fake_progress for task {task_id}: {e}", exc_info=True)
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
                logger.error(f"Error in background simulate thread for task {task_id}: {e}", exc_info=True)
        
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
    task = _svc(request).retry_task(
        task_id, background=background
    )
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
