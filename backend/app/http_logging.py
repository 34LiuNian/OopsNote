from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable

from fastapi import Request
from starlette.responses import Response

from .request_context import reset_request_id, set_request_id
from .trace import trace_event

logger = logging.getLogger(__name__)


class DropHealthAccessLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        if " /health " in message:
            return False
        if "GET /tasks?active_only=true" in message:
            return False
        if " /tasks/" in message and " /events " in message:
            return False
        if "OPTIONS /tasks/" in message and " /process?background=true" in message:
            return False
        return True


def configure_app_logging() -> None:
    app_log_level = os.getenv("APP_LOG_LEVEL")
    if (
        os.getenv("AI_DEBUG_LLM", "false").lower() == "true"
        or os.getenv("AI_DEBUG_LLM_PAYLOAD", "false").lower() == "true"
    ) and not app_log_level:
        app_log_level = "INFO"
    if app_log_level:
        logging.getLogger().setLevel(
            getattr(logging, app_log_level.upper(), logging.INFO)
        )

    logging.getLogger("uvicorn.access").addFilter(DropHealthAccessLogs())


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = set_request_id(rid)
    started = time.perf_counter()
    is_health = request.url.path == "/health"
    if not is_health:
        logger.info("HTTP in rid=%s %s %s", rid, request.method, request.url.path)
        trace_event(
            "http_in",
            method=request.method,
            path=request.url.path,
            query=str(request.url.query),
            user_agent=request.headers.get("user-agent"),
            origin=request.headers.get("origin"),
        )
    try:
        response = await call_next(request)
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        status = getattr(locals().get("response"), "status_code", "-")
        if not is_health:
            logger.info("HTTP out rid=%s status=%s ms=%.1f", rid, status, elapsed_ms)
            trace_event("http_out", status=status, ms=elapsed_ms)
        reset_request_id(token)

    response.headers["x-request-id"] = rid
    return response
