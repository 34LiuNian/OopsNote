from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import (
    AgentEnabledResponse,
    AgentEnabledUpdateRequest,
    AgentModelsResponse,
    AgentModelsUpdateRequest,
    AgentThinkingResponse,
    AgentThinkingUpdateRequest,
)

router = APIRouter()


def _service(request: Request):
    state = getattr(request.app.state, "oops", None)
    return getattr(state, "agent_settings", None)


@router.get("/settings/agent-models", response_model=AgentModelsResponse)
def get_agent_models(request: Request) -> AgentModelsResponse:
    svc = _service(request)
    return AgentModelsResponse(models=svc.load_models())


@router.put("/settings/agent-models", response_model=AgentModelsResponse)
def update_agent_models(
    request: Request, payload: AgentModelsUpdateRequest
) -> AgentModelsResponse:
    svc = _service(request)
    saved = svc.save_models(payload.models)
    return AgentModelsResponse(models=saved)


@router.get("/settings/agent-enabled", response_model=AgentEnabledResponse)
def get_agent_enabled(request: Request) -> AgentEnabledResponse:
    svc = _service(request)
    return AgentEnabledResponse(enabled=svc.enabled_snapshot())


@router.put("/settings/agent-enabled", response_model=AgentEnabledResponse)
def update_agent_enabled(
    request: Request, payload: AgentEnabledUpdateRequest
) -> AgentEnabledResponse:
    svc = _service(request)
    saved = svc.save_enabled(payload.enabled)
    return AgentEnabledResponse(enabled=saved)


@router.get("/settings/agent-thinking", response_model=AgentThinkingResponse)
def get_agent_thinking(request: Request) -> AgentThinkingResponse:
    svc = _service(request)
    return AgentThinkingResponse(thinking=svc.thinking_snapshot())


@router.put("/settings/agent-thinking", response_model=AgentThinkingResponse)
def update_agent_thinking(
    request: Request, payload: AgentThinkingUpdateRequest
) -> AgentThinkingResponse:
    svc = _service(request)
    saved = svc.save_thinking(payload.thinking)
    return AgentThinkingResponse(thinking=saved)
