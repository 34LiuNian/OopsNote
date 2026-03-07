"""Problem-level operations API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..auth.deps import require_user
from ..models import ProblemsResponse
from .deps import get_tasks_service

router = APIRouter(dependencies=[Depends(require_user)])


def _service(request: Request):
    """Resolve task service from shared API dependencies."""
    return get_tasks_service(request)


@router.get("/problems", response_model=ProblemsResponse)
def list_problems(
    request: Request,
    subject: str | None = None,
    tag: str | None = None,
    source: str | None = Query(  # pylint: disable=unused-argument
        None, description="Source filter (can be repeated for OR logic)"
    ),
    knowledge_tag: str | None = Query(  # pylint: disable=unused-argument
        None, description="Knowledge tag filter (can be repeated for OR logic)"
    ),
    error_tag: str | None = Query(  # pylint: disable=unused-argument
        None, description="Error tag filter (can be repeated for OR logic)"
    ),
    user_tag: str | None = Query(  # pylint: disable=unused-argument
        None, description="Custom tag filter (can be repeated for OR logic)"
    ),
    created_after: str | None = Query(
        None, description="Filter problems created after this date (ISO 8601 format)"
    ),
    created_before: str | None = Query(
        None, description="Filter problems created before this date (ISO 8601 format)"
    ),
) -> ProblemsResponse:
    # FastAPI automatically handles repeated query params as lists
    # Access the raw query params to get all values
    query_params = request.query_params
    source_list = query_params.getlist("source") if "source" in query_params else None
    knowledge_tag_list = (
        query_params.getlist("knowledge_tag")
        if "knowledge_tag" in query_params
        else None
    )
    error_tag_list = (
        query_params.getlist("error_tag") if "error_tag" in query_params else None
    )
    user_tag_list = (
        query_params.getlist("user_tag") if "user_tag" in query_params else None
    )

    svc = _service(request)
    return svc.list_problems(
        subject=subject,
        tag=tag,
        source=source_list,
        knowledge_tag=knowledge_tag_list,
        error_tag=error_tag_list,
        user_tag=user_tag_list,
        created_after=created_after,
        created_before=created_before,
    )
