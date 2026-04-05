from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth.deps import require_admin, require_user
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

router = APIRouter(dependencies=[Depends(require_user)])


def _svc(request: Request):
    """从通用 API 依赖中解析任务服务。"""
    return get_tasks_service(request)


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    request: Request, payload: TaskCreateRequest, auto_process: bool = True
) -> TaskResponse:
    """创建新任务。

    Args:
        request: HTTP 请求
        payload: 任务创建载荷
        auto_process: 是否立即启动处理

    Returns:
        创建后的任务响应
    """
    task = _svc(request).create_task(payload, auto_process=auto_process)
    return TaskResponse(task=task)


@router.get("/tasks", response_model=TasksResponse)
def list_tasks(
    request: Request,
    status: TaskStatus | None = None,
    active_only: bool = True,  # 默认仅返回活跃任务，用于展示进行中的任务
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


@router.post(
    "/tasks/{task_id}/problems/{problem_id}/diagram", response_model=TaskResponse
)
def rerender_diagram(request: Request, task_id: str, problem_id: str) -> TaskResponse:
    task = _svc(request).rerender_diagram(task_id, problem_id)
    return TaskResponse(task=task)


@router.patch(
    "/tasks/{task_id}/problems/{problem_id}/override", response_model=TaskResponse
)
def override_problem(
    request: Request, task_id: str, problem_id: str, override: OverrideProblemRequest
) -> TaskResponse:
    task = _svc(request).override_problem(task_id, problem_id, override)
    return TaskResponse(task=task)


@router.delete(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_admin)],
)
def delete_task(request: Request, task_id: str) -> TaskResponse:
    task = _svc(request).delete_task(task_id)
    return TaskResponse(task=task)


@router.delete(
    "/tasks/{task_id}/problems/{problem_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_admin)],
)
def delete_problem(request: Request, task_id: str, problem_id: str) -> TaskResponse:
    task = _svc(request).delete_problem(task_id, problem_id)
    return TaskResponse(task=task)


@router.post(
    "/tasks/{task_id}/problems/{problem_id}/retry", response_model=TaskResponse
)
def retry_problem(request: Request, task_id: str, problem_id: str) -> TaskResponse:
    task = _svc(request).retry_problem(task_id, problem_id)
    return TaskResponse(task=task)
