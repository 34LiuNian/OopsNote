from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import ProblemsResponse

router = APIRouter()


@router.get("/problems", response_model=ProblemsResponse)
def list_problems(request: Request, subject: str | None = None, tag: str | None = None) -> ProblemsResponse:
    state = getattr(request.app.state, "oops", None)
    svc = getattr(state, "tasks", None)
    return svc.list_problems(subject=subject, tag=tag)
