from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    state = getattr(request.app.state, "oops", None)
    ai_gateway = getattr(state, "ai_gateway_status", {"checked": False})
    return {
        "status": "ok",
        "ai_gateway": ai_gateway,
    }
