from __future__ import annotations

from fastapi import HTTPException, Request


def get_backend_state(request: Request):
    """Return backend state object from app and fail fast when missing."""
    state = getattr(request.app.state, "oops", None)
    if state is None:
        raise HTTPException(status_code=500, detail="Backend state unavailable")
    return state


def get_tasks_service(request: Request):
    """Return task service from backend state and fail fast when unavailable."""
    state = get_backend_state(request)
    service = getattr(state, "tasks", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Tasks service unavailable")
    return service


def get_models_service(request: Request):
    """Return models service from backend state and fail fast when unavailable."""
    state = get_backend_state(request)
    service = getattr(state, "models", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Models service unavailable")
    return service


def get_agent_settings_service(request: Request):
    """Return agent settings service from backend state and fail fast when unavailable."""
    state = get_backend_state(request)
    service = getattr(state, "agent_settings", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Agent settings service unavailable")
    return service
