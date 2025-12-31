from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import ModelsResponse, ModelSummary

router = APIRouter()


@router.get("/models", response_model=ModelsResponse)
def list_models(request: Request, refresh: bool = False) -> ModelsResponse:
    state = getattr(request.app.state, "oops", None)
    svc = getattr(state, "models", None)
    items = svc.list_models(refresh=refresh)
    return ModelsResponse(items=[ModelSummary(**m) for m in items if m.get("id")])
