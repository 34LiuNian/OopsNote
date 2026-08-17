"""OCR tool shared by restricted managed-worker transports."""

from __future__ import annotations

import base64
import contextlib
import json
import mimetypes
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from oopsnote.ai.skills import load_skill_prompt
from oopsnote.core import OcrPrintedContext, RunArtifact, StateConflict, TaskStage, TaskStatus
from oopsnote.mcp.ocr_contract import normalize_ocr_result

MAX_IMAGE_BYTES = 12 * 1024 * 1024
OCR_INSTRUCTION = load_skill_prompt(Path(__file__).resolve().parents[2], "oopsnote-ocr-extract")
_OCR_RESULT_LOCK = threading.Lock()
_OCR_RESULTS: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
_OCR_RESULT_LIMIT = 128
_RUN_MODEL_RESOLVER: Callable[[str], Any] | None = None
_JSON_FENCE = re.compile(
    r"^\s*```(?:json)?\s*\n?(?P<body>\{.*\})\s*```\s*$", re.IGNORECASE | re.DOTALL
)


class OcrProviderError(RuntimeError):
    """A classified OCR boundary failure suitable for lifecycle policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def clear_ocr_results() -> None:
    """Clear per-run OCR memoization during application shutdown or tests."""
    with _OCR_RESULT_LOCK:
        _OCR_RESULTS.clear()


def configure_ocr_run_model_resolver(resolver: Callable[[str], Any]) -> None:
    """Resolve a vision model from an immutable run snapshot at the MCP boundary."""
    global _RUN_MODEL_RESOLVER
    _RUN_MODEL_RESOLVER = resolver


def clear_ocr_run_model_resolver() -> None:
    global _RUN_MODEL_RESOLVER
    _RUN_MODEL_RESOLVER = None


def _vision_json_object(content: Any) -> dict[str, Any]:
    """Parse one provider response without accepting explanatory prose.

    Providers commonly wrap an otherwise valid JSON response in one Markdown
    fence. The Vision adapter owns that transport normalization; the OCR
    contract remains the sole authority for the resulting object.
    """

    if isinstance(content, list):
        content = "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content
        )
    if isinstance(content, dict):
        return content
    text = str(content).strip()
    fenced = _JSON_FENCE.fullmatch(text)
    if fenced:
        text = fenced.group("body")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Vision model returned a non-object OCR result")
    return parsed


def _ocr_image_path(image_path: Path, vision_model: Any) -> dict[str, Any]:
    """Send one already-authorized managed image to the OCR provider."""
    mime, _ = mimetypes.guess_type(image_path.name)
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError("Unsupported OCR image type")
    try:
        image = image_path.read_bytes()
    except OSError as error:
        raise ValueError(f"OCR image cannot be read: {image_path}") from error
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("OCR image exceeds 12 MiB limit")

    try:
        from langchain_core.messages import HumanMessage

        content = vision_model.invoke(
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": OCR_INSTRUCTION},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
                            },
                        },
                    ]
                )
            ]
        )
        content = getattr(content, "content", content)
        return _vision_json_object(content)
    except OcrProviderError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise OcrProviderError(
            "ocr_invalid_response", "Vision model returned an invalid OCR response"
        ) from error
    except Exception as error:
        status = getattr(error, "status_code", None)
        if status is None:
            status = getattr(getattr(error, "response", None), "status_code", None)
        if status in {401, 403}:
            code = "ocr_authorization"
        elif status == 429:
            code = "ocr_rate_limit"
        elif status in {408, 500, 502, 503, 504}:
            code = "ocr_provider_unavailable"
        elif isinstance(error, (httpx.TimeoutException, TimeoutError)):
            code = "ocr_timeout"
        elif isinstance(error, (httpx.TransportError, ConnectionError)):
            code = "ocr_network_error"
        else:
            code = "ocr_provider_error"
        raise OcrProviderError(code, "Vision model OCR request failed") from error


def ocr_image(task_id: str, run_id: str) -> dict[str, Any]:
    """OCR only the asset bound to the currently active managed task run."""
    # Imported lazily to keep the provider client independent from store setup
    # and to let tests replace the shared MCP stores.
    from oopsnote.mcp import server

    stores = server._stores()
    task = stores.task_store.get(task_id)
    if not run_id or task.active_run_id != run_id:
        raise ValueError(f"run_id {run_id} is not active for task {task_id}")
    run = server._active_task_run(task_id, run_id)
    if not task.asset_path:
        raise ValueError(f"task {task_id} has no image asset")
    cache_key = (task_id, run_id, task.asset_path)
    with _OCR_RESULT_LOCK:
        cached = _OCR_RESULTS.get(cache_key)
        if cached is not None:
            _OCR_RESULTS.move_to_end(cache_key)
            return deepcopy(cached)
    image_path = stores.asset_store.resolve(task.asset_path)
    snapshot = run.provider_profile_snapshot
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("vision"), dict):
        raise RuntimeError("Run has no LangChain Vision snapshot")
    if _RUN_MODEL_RESOLVER is None:
        raise RuntimeError("LangChain Vision resolver is unavailable")
    vision_model = _RUN_MODEL_RESOLVER(run_id)
    if vision_model is None:
        raise RuntimeError("LangChain Vision model is unavailable")
    parsed = _ocr_image_path(image_path, vision_model)
    expected_question_no = task.metadata.get("question_no") or task.metadata.get(
        "batch_question_no"
    )
    try:
        result = normalize_ocr_result(
            parsed,
            expected_question_no=expected_question_no,
        )
    except ValueError as error:
        raise OcrProviderError(
            "ocr_invalid_response",
            f"DashScope OCR returned an invalid result: {error}",
        ) from error
    stores.run_store.record_artifact(
        run.id,
        RunArtifact(
            stage=TaskStage.OCR,
            kind="ocr",
            raw_output=json.dumps(parsed, ensure_ascii=False, sort_keys=True),
            parsed_output=result,
        ),
    )
    with contextlib.suppress(StateConflict):
        # A cancelled or replaced run must not attach stale OCR observations.
        stores.task_store.transition(
            task_id,
            expected_statuses={TaskStatus.PROCESSING},
            expected_active_run_id=run_id,
            ocr_context=OcrPrintedContext(
                printed_question_no=result.get("printed_question_no"),
                printed_chapter=result.get("printed_chapter"),
            ),
        )
    with _OCR_RESULT_LOCK:
        _OCR_RESULTS[cache_key] = deepcopy(result)
        _OCR_RESULTS.move_to_end(cache_key)
        while len(_OCR_RESULTS) > _OCR_RESULT_LIMIT:
            _OCR_RESULTS.popitem(last=False)
    return result


__all__ = [
    "OCR_INSTRUCTION",
    "OcrProviderError",
    "clear_ocr_results",
    "clear_ocr_run_model_resolver",
    "configure_ocr_run_model_resolver",
    "ocr_image",
]
