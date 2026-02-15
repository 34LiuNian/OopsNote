from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import ProblemsResponse
from .deps import get_tasks_service

router = APIRouter()


def _service(request: Request):
    """Resolve task service from shared API dependencies."""
    return get_tasks_service(request)


@router.get("/problems", response_model=ProblemsResponse)
def list_problems(
    request: Request, subject: str | None = None, tag: str | None = None
) -> ProblemsResponse:
    svc = _service(request)
    return svc.list_problems(subject=subject, tag=tag)
