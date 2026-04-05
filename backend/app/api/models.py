"""模型管理相关 API 端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.deps import require_user
from ..models import ModelsResponse, ModelSummary
from ..services.models_service import ModelsServiceConfigError
from .deps import get_models_service

router = APIRouter(dependencies=[Depends(require_user)])


def _service(request: Request):
    """从通用 API 依赖中解析模型服务。"""
    return get_models_service(request)


@router.get("/models", response_model=ModelsResponse)
def list_models(request: Request, refresh: bool = False) -> ModelsResponse:
    svc = _service(request)
    try:
        items = svc.list_models(refresh=refresh)
    except ModelsServiceConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModelsResponse(items=[ModelSummary(**m) for m in items if m.get("id")])
