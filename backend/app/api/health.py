from __future__ import annotations

from fastapi import APIRouter, Request
from .deps import get_backend_state

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    state = get_backend_state(request)
    ai_gateway = getattr(state, "ai_gateway_status", {"checked": False})
    return {
        "status": "ok",
        "ai_gateway": ai_gateway,
    }
