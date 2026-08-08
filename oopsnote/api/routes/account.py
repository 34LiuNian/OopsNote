"""Authenticated user's own account projections."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from oopsnote.core import Principal

router = APIRouter(prefix="/me", tags=["account"])


@router.get("/quota")
def get_own_quota(request: Request) -> dict[str, Any]:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="Missing authenticated user")
    from oopsnote.api import main

    quota = main.WORKSPACE_REGISTRY.quota_summary(principal.user_id)
    if quota is None:
        raise HTTPException(status_code=404, detail="Workspace quota not found")
    return {"quota": quota}


__all__ = ["router"]
