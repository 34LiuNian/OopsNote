"""API 路由的依赖注入辅助函数。"""

from __future__ import annotations

from fastapi import HTTPException, Request


def get_backend_state(request: Request):
    """从 app.state 获取后端状态对象；缺失时立即报错。"""
    state = getattr(request.app.state, "oops", None)
    if state is None:
        raise HTTPException(status_code=500, detail="Backend state unavailable")
    return state


def get_tasks_service(request: Request):
    """从后端状态获取任务服务；不可用时立即报错。"""
    state = get_backend_state(request)
    service = getattr(state, "tasks", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Tasks service unavailable")
    return service


def get_models_service(request: Request):
    """从后端状态获取模型服务；不可用时立即报错。"""
    state = get_backend_state(request)
    service = getattr(state, "models", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Models service unavailable")
    return service


def get_agent_settings_service(request: Request):
    """从后端状态获取 Agent 设置服务；不可用时立即报错。"""
    state = get_backend_state(request)
    service = getattr(state, "agent_settings", None)
    if service is None:
        raise HTTPException(
            status_code=500, detail="Agent settings service unavailable"
        )
    return service


def get_auth_settings_service(request: Request):
    """从后端状态获取认证设置服务；不可用时立即报错。"""
    state = get_backend_state(request)
    service = getattr(state, "auth_settings", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Auth settings service unavailable")
    return service
