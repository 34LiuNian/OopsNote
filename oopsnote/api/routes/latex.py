"""API boundary for the authoritative internal LaTeX renderer."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

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
        raise HTTPException(
            status_code=422,
            detail={"code": first.code, "message": first.message, "line": first.line},
        )
    renderer_url = _renderer_url()
    if not renderer_url:
        raise HTTPException(
            status_code=503,
            detail={"code": "renderer-unavailable", "message": "LaTeX renderer is not configured"},
        )
    try:
        result = httpx.post(
            f"{renderer_url}/v1/tikz",
            json={"source": source},
            timeout=35,
        )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail={"code": "renderer-timeout", "message": "TikZ rendering timed out"},
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "renderer-unavailable", "message": str(error)},
        ) from error
    if result.status_code != 200:
        raise HTTPException(
            status_code=422 if result.status_code < 500 else 503,
            detail={"code": "renderer-failed", "message": result.text[-12_000:]},
        )
    return Response(content=result.content, media_type="image/svg+xml")
