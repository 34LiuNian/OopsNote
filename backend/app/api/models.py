from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi import HTTPException

from ..models import ModelsResponse, ModelSummary
from ..services.models_service import ModelsServiceConfigError
from .deps import get_models_service

router = APIRouter()


def _service(request: Request):
    """Resolve models service from shared API dependencies."""
    return get_models_service(request)


@router.get("/models", response_model=ModelsResponse)
def list_models(request: Request, refresh: bool = False) -> ModelsResponse:
    svc = _service(request)
    try:
        items = svc.list_models(refresh=refresh)
    except ModelsServiceConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModelsResponse(items=[ModelSummary(**m) for m in items if m.get("id")])
