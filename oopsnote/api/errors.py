"""Stable REST error taxonomy and context-bearing error responses."""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException


class ApiErrorCategory(str, Enum):
    REQUEST = "request"
    MODEL_REQUEST = "model_request"
    TIKZ_COMPILE = "tikz_compile"
    HUMAN_REVIEW = "human_review"
    INTERNAL = "internal"


_MODEL_CODES = frozenset({
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
})
_TIKZ_CODES = frozenset({
    "invalid_tikz_source",
    "renderer_contract_error",
    "renderer_failed",
    "renderer_timeout",
    "renderer_unavailable",
})
_REVIEW_CODES = frozenset({
    "diagram_candidate_limit",
    "ocr_unreadable",
    "ocr_incomplete",
    "ocr_multiple_questions",
})


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
    "scope_for_path",
]
