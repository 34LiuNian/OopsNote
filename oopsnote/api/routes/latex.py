"""API boundary for the authoritative internal LaTeX renderer."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from oopsnote.api.errors import ApiErrorCategory, api_error
from oopsnote.content import validate_oopsmark

router = APIRouter(prefix="/latex")


class TikzRenderRequest(BaseModel):
    source: str = Field(min_length=1, max_length=80_000)


def _renderer_url() -> str:
    return os.getenv("OOPSNOTE_LATEX_RENDERER_URL", "").rstrip("/")


@router.post("/tikz")
def render_tikz(payload: TikzRenderRequest) -> Response:
    source = payload.source.strip()
    issues = validate_oopsmark(f"```tikz\n{source}\n```")
    if issues:
        first = issues[0]
        raise api_error(
            422,
            code=first.code,
            message=first.message,
            category=ApiErrorCategory.TIKZ_COMPILE,
            scope="tikz_render",
            details={"line": first.line} if first.line is not None else None,
        )
    renderer_url = _renderer_url()
    if not renderer_url:
        raise api_error(
            503,
            code="renderer_unavailable",
            message="LaTeX renderer is not configured",
            category=ApiErrorCategory.TIKZ_COMPILE,
            scope="tikz_render",
        )
    try:
        result = httpx.post(
            f"{renderer_url}/v1/tikz",
            json={"source": source},
            timeout=35,
        )
    except httpx.TimeoutException as error:
        raise api_error(
            504,
            code="renderer_timeout",
            message="TikZ rendering timed out",
            category=ApiErrorCategory.TIKZ_COMPILE,
            retryable=True,
            scope="tikz_render",
        ) from error
    except httpx.HTTPError as error:
        raise api_error(
            503,
            code="renderer_unavailable",
            message=str(error),
            category=ApiErrorCategory.TIKZ_COMPILE,
            retryable=True,
            scope="tikz_render",
        ) from error
    if result.status_code != 200:
        retryable = result.status_code >= 500
        raise api_error(
            503 if retryable else 422,
            code="renderer_failed",
            message=result.text[-12_000:],
            category=ApiErrorCategory.TIKZ_COMPILE,
            retryable=retryable,
            scope="tikz_render",
        )
    return Response(content=result.content, media_type="image/svg+xml")
