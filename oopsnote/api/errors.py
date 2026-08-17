"""Stable REST error taxonomy and context-bearing error responses."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from fastapi import HTTPException


class ApiErrorCategory(StrEnum):
    REQUEST = "request"
    MODEL_REQUEST = "model_request"
    TIKZ_COMPILE = "tikz_compile"
    HUMAN_REVIEW = "human_review"
    INTERNAL = "internal"


_MODEL_CODES = frozenset(
    {
        "connection_error",
        "network_error",
        "ocr_network_error",
        "ocr_provider_unavailable",
        "ocr_rate_limit",
        "ocr_timeout",
        "provider_authorization",
        "provider_model_unavailable",
        "provider_rate_limit",
        "provider_unavailable",
        "rate_limit",
        "rate_limit_exceeded",
        "service_unavailable",
        "model_output_invalid",
        "diagram_runner_unavailable",
    }
)
_TIKZ_CODES = frozenset(
    {
        "invalid_tikz_source",
        "renderer_contract_error",
        "renderer_failed",
        "renderer_timeout",
        "renderer_unavailable",
    }
)
_REVIEW_CODES = frozenset(
    {
        "diagram_candidate_limit",
        "renderer_environment_error",
        "ocr_unreadable",
        "ocr_incomplete",
        "ocr_multiple_questions",
    }
)
_SUPPLIER_CODES = frozenset(
    {
        "connection_error",
        "network_error",
        "ocr_network_error",
        "ocr_provider_unavailable",
        "ocr_rate_limit",
        "ocr_timeout",
        "provider_authorization",
        "provider_model_unavailable",
        "provider_rate_limit",
        "provider_unavailable",
        "rate_limit",
        "rate_limit_exceeded",
        "service_unavailable",
    }
)

_HTTP_STATUS_PATTERN = re.compile(r"(?<!\d)([45]\d{2})(?!\d)")
_HTML_TITLE_HOST_PATTERN = re.compile(
    r"<title>\s*([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)\s*\|",
    re.IGNORECASE,
)


def _http_status_from_message(message: str | None) -> int | None:
    match = _HTTP_STATUS_PATTERN.search(message or "")
    return int(match.group(1)) if match else None


def public_error_code(code: str | None, message: str | None = None) -> str | None:
    """Project legacy unclassified provider 5xx evidence onto the REST taxonomy."""

    normalized = (code or "").strip().lower() or None
    status = _http_status_from_message(message)
    if normalized in {None, "runner_error", "validation_failed"} and (
        "may only use the active task_id" in (message or "")
        or "may only use the active run_id" in (message or "")
    ):
        return "model_output_invalid"
    if (
        normalized in {None, "runner_error", "validation_failed"}
        and status is not None
        and 500 <= status <= 599
    ):
        return "provider_unavailable"
    return normalized


def public_error_message(code: str | None, message: str | None) -> str | None:
    """Return a concise public failure message while retaining raw local evidence."""

    if not message:
        return None
    public_code = public_error_code(code, message)
    if public_code == "model_output_invalid":
        return f"模型输出不符合工具协议：{message}"
    if public_code == "renderer_environment_error":
        return "TikZ 渲染服务环境异常，需要人工介入修复"
    if public_code not in _SUPPLIER_CODES:
        return message
    if message.startswith("供应商侧请求失败："):
        return message

    status = _http_status_from_message(message)
    looks_like_markup = "<!doctype html" in message.lower() or "<html" in message.lower()
    if public_code == "provider_unavailable" and (looks_like_markup or status == 524):
        host_match = _HTML_TITLE_HOST_PATTERN.search(message)
        host = host_match.group(1) if host_match else "上游网关"
        if status == 524:
            return f"供应商侧请求失败：{host} 网关响应超时（HTTP 524）"
        if status is not None:
            return f"供应商侧请求失败：{host} 暂时不可用（HTTP {status}）"
        return f"供应商侧请求失败：{host} 暂时不可用"
    return f"供应商侧请求失败：{message}"


def category_for_error_code(
    code: str | None,
    *,
    needs_review: bool = False,
) -> ApiErrorCategory:
    """Map one persisted error code to the authoritative REST category."""

    normalized = (code or "").strip().lower()
    if normalized in _TIKZ_CODES:
        return ApiErrorCategory.TIKZ_COMPILE
    if normalized in _MODEL_CODES:
        return ApiErrorCategory.MODEL_REQUEST
    if normalized in _REVIEW_CODES or (needs_review and not normalized):
        return ApiErrorCategory.HUMAN_REVIEW
    if normalized in {
        "task_not_found",
        "problem_not_found",
        "question_not_ready",
        "source_image_missing",
        "task_busy",
        "diagram_run_active",
        "candidate_not_found",
        "candidate_not_rendered",
        "diagram_item_not_found",
        "tikz_source_missing",
        "task_cancel_conflict",
        "admission_conflict",
        "backend_unreachable",
        "batch_session_not_found",
        "batch_source_unavailable",
        "batch_source_too_large",
        "batch_source_invalid",
        "batch_page_count_invalid",
        "batch_revision_conflict",
        "batch_segment_not_found",
        "batch_crop_unconfirmed",
        "request_invalid",
    }:
        return ApiErrorCategory.REQUEST
    return ApiErrorCategory.INTERNAL


def error_detail(
    *,
    code: str,
    message: str,
    category: ApiErrorCategory | None = None,
    retryable: bool = False,
    scope: str = "request",
    task_id: str | None = None,
    run_id: str | None = None,
    diagram_item_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": (category or category_for_error_code(code)).value,
        "code": code,
        "message": message,
        "retryable": retryable,
        "scope": scope,
    }
    for key, value in (
        ("task_id", task_id),
        ("run_id", run_id),
        ("diagram_item_id", diagram_item_id),
    ):
        if value is not None:
            payload[key] = value
    if details:
        payload["details"] = details
    return payload


def api_error(
    status_code: int,
    *,
    code: str,
    message: str,
    category: ApiErrorCategory | None = None,
    retryable: bool = False,
    scope: str = "request",
    task_id: str | None = None,
    run_id: str | None = None,
    diagram_item_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_detail(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            scope=scope,
            task_id=task_id,
            run_id=run_id,
            diagram_item_id=diagram_item_id,
            details=details,
        ),
    )


def scope_for_path(path: str) -> str:
    if path.startswith("/tasks/") and "/problem/override" in path:
        return "problem_edit"
    if path.startswith("/tasks/") and "/diagrams" in path:
        return "diagram"
    if path.startswith("/tasks") or path.startswith("/upload"):
        return "task"
    if path.startswith("/batch-sessions"):
        return "batch"
    if path.startswith("/papers"):
        return "paper"
    if path.startswith("/latex"):
        return "tikz_render"
    if path.startswith("/settings/ai"):
        return "ai_settings"
    return "request"


__all__ = [
    "ApiErrorCategory",
    "api_error",
    "category_for_error_code",
    "error_detail",
    "public_error_code",
    "public_error_message",
    "scope_for_path",
]
