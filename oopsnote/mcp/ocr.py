"""OCR tool shared by restricted managed-worker transports."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import threading
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any
from collections.abc import Callable

import httpx

from oopsnote.core import OcrPrintedContext, RunArtifact, StateConflict, TaskStage, TaskStatus
from oopsnote.mcp.ocr_contract import OCR_INSTRUCTION, normalize_ocr_result
from oopsnote.ai.secrets import SecretStore, SecretNotFoundError


MAX_IMAGE_BYTES = 12 * 1024 * 1024
DEFAULT_OCR_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
# Backward-compatible public name used by integrations and tests.
OCR_ENDPOINT = DEFAULT_OCR_ENDPOINT
_OCR_CLIENT: httpx.Client | None = None
_OCR_CLIENT_LOCK = threading.Lock()
_OCR_RESULT_LOCK = threading.Lock()
_OCR_RESULTS: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
_OCR_RESULT_LIMIT = 128
_VAULT_SECRET_STORE: SecretStore | None = None
_VAULT_CREDENTIAL_REF: str | None = None
_VAULT_OCR_CONFIG: dict[str, Any] = {}
_RUN_MODEL_RESOLVER: Callable[[str], Any] | None = None
_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?(?P<body>\{.*\})\s*```\s*$", re.IGNORECASE | re.DOTALL)


class OcrProviderError(RuntimeError):
    """A classified OCR boundary failure suitable for lifecycle policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _ocr_client() -> httpx.Client:
    global _OCR_CLIENT
    with _OCR_CLIENT_LOCK:
        if _OCR_CLIENT is None:
            _OCR_CLIENT = httpx.Client(timeout=90)
        return _OCR_CLIENT


def close_ocr_client() -> None:
    """Close pooled provider connections and clear per-run OCR memoization."""

    global _OCR_CLIENT
    with _OCR_CLIENT_LOCK:
        client = _OCR_CLIENT
        _OCR_CLIENT = None
    if client is not None:
        client.close()
    with _OCR_RESULT_LOCK:
        _OCR_RESULTS.clear()


def configure_ocr_vault(secret_store: SecretStore, credential_ref: str, *, model: str, endpoint: str | None = None) -> None:
    """Configure OCR to resolve credentials from the OopsNote vault."""
    global _VAULT_SECRET_STORE, _VAULT_CREDENTIAL_REF, _VAULT_OCR_CONFIG
    _VAULT_SECRET_STORE = secret_store
    _VAULT_CREDENTIAL_REF = credential_ref
    _VAULT_OCR_CONFIG = {"model": model, **({"endpoint": endpoint} if endpoint else {})}


def clear_ocr_vault() -> None:
    """Clear process-local vault wiring during application shutdown or tests."""
    global _VAULT_SECRET_STORE, _VAULT_CREDENTIAL_REF, _VAULT_OCR_CONFIG
    _VAULT_SECRET_STORE = None
    _VAULT_CREDENTIAL_REF = None
    _VAULT_OCR_CONFIG = {}


def configure_ocr_run_model_resolver(resolver: Callable[[str], Any]) -> None:
    """Resolve a vision model from an immutable run snapshot at the MCP boundary."""
    global _RUN_MODEL_RESOLVER
    _RUN_MODEL_RESOLVER = resolver


def clear_ocr_run_model_resolver() -> None:
    global _RUN_MODEL_RESOLVER
    _RUN_MODEL_RESOLVER = None


def ocr_vault_is_configured() -> bool:
    return _VAULT_SECRET_STORE is not None and bool(_VAULT_CREDENTIAL_REF)


def _load_ocr_config() -> dict[str, Any]:
    if _VAULT_SECRET_STORE is not None and _VAULT_CREDENTIAL_REF:
        try:
            secret = _VAULT_SECRET_STORE.get(_VAULT_CREDENTIAL_REF)
        except SecretNotFoundError as error:
            raise RuntimeError("OCR credential reference is unavailable") from error
        return {**_VAULT_OCR_CONFIG, "dashscope_api_key": secret}
    configured = os.getenv("OOPSNOTE_OCR_CONFIG")
    path = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[2] / ".pi" / "extensions.json"
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"OCR configuration is unavailable: {path}") from error
    config = data.get("ocr_image") if isinstance(data, dict) else None
    if not isinstance(config, dict):
        raise RuntimeError(f"OCR configuration is invalid: {path}")
    return config


def _vision_json_object(content: Any) -> dict[str, Any]:
    """Parse one provider response without accepting explanatory prose.

    Providers commonly wrap an otherwise valid JSON response in one Markdown
    fence. The Vision adapter owns that transport normalization; the OCR
    contract remains the sole authority for the resulting object.
    """

    if isinstance(content, list):
        content = "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
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


def _ocr_image_path(image_path: Path, vision_model: Any | None = None) -> dict[str, Any]:
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

    if vision_model is not None:
        try:
            from langchain_core.messages import HumanMessage

            content = vision_model.invoke([HumanMessage(content=[
                {"type": "text", "text": OCR_INSTRUCTION},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"}},
            ])])
            content = getattr(content, "content", content)
            parsed = _vision_json_object(content)
        except OcrProviderError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise OcrProviderError("ocr_invalid_response", "Vision model returned an invalid OCR response") from error
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
            else:
                is_transport = isinstance(error, httpx.TransportError)
                is_timeout = isinstance(error, httpx.TimeoutException)
                if is_timeout or isinstance(error, (TimeoutError,)):  # noqa: UP038
                    code = "ocr_timeout"
                elif is_transport or isinstance(error, ConnectionError):
                    code = "ocr_network_error"
                else:
                    code = "ocr_provider_error"
            raise OcrProviderError(code, "Vision model OCR request failed") from error
        return parsed

    config = _load_ocr_config()
    api_key = str(config.get("dashscope_api_key") or "")
    model = str(config.get("model") or "")
    endpoint = str(config.get("endpoint") or DEFAULT_OCR_ENDPOINT)
    if not api_key or not model:
        raise RuntimeError("OCR key and model are required in .pi/extensions.json")

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                f"data:{mime};base64,"
                                f"{base64.b64encode(image).decode('ascii')}"
                            )
                        },
                    },
                    {"type": "text", "text": OCR_INSTRUCTION},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        response = _ocr_client().post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status == 429:
            raise OcrProviderError(
                "ocr_rate_limit",
                f"DashScope OCR rate limit: HTTP {status}",
            ) from error
        if status in {408, 500, 502, 503, 504}:
            raise OcrProviderError(
                "ocr_provider_unavailable",
                f"DashScope OCR provider unavailable: HTTP {status}",
            ) from error
        raise OcrProviderError(
            "ocr_provider_error",
            f"DashScope OCR provider error: HTTP {status}",
        ) from error
    except httpx.TimeoutException as error:
        raise OcrProviderError("ocr_timeout", "DashScope OCR timeout") from error
    except httpx.TransportError as error:
        raise OcrProviderError(
            "ocr_network_error",
            f"DashScope OCR network error: {error}",
        ) from error
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise OcrProviderError(
            "ocr_invalid_response",
            "DashScope OCR returned an invalid response",
        ) from error
    if not isinstance(parsed, dict):
        raise OcrProviderError(
            "ocr_invalid_response",
            "DashScope OCR returned a non-object result",
        )
    return parsed


def ocr_image(task_id: str, run_id: str) -> dict[str, Any]:
    """OCR only the asset bound to the currently active managed task run."""
    # Imported lazily to keep the provider client independent from store setup
    # and to let tests replace the shared MCP stores.
    from oopsnote.mcp import server

    task = server.TASK_STORE.get(task_id)
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
    image_path = server.ASSET_STORE.resolve(task.asset_path)
    snapshot = run.provider_profile_snapshot
    is_langchain_snapshot = isinstance(snapshot, dict) and isinstance(snapshot.get("vision"), dict)
    if is_langchain_snapshot and _RUN_MODEL_RESOLVER is None:
        raise RuntimeError("LangChain Vision resolver is unavailable")
    vision_model = _RUN_MODEL_RESOLVER(run_id) if _RUN_MODEL_RESOLVER is not None else None
    if is_langchain_snapshot and vision_model is None:
        raise RuntimeError("LangChain Vision model is unavailable")
    parsed = _ocr_image_path(image_path, vision_model) if vision_model is not None else _ocr_image_path(image_path)
    expected_question_no = (
        task.metadata.get("question_no")
        or task.metadata.get("batch_question_no")
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
    server.RUN_STORE.record_artifact(
        run.id,
        RunArtifact(
            stage=TaskStage.OCR,
            kind="ocr",
            raw_output=json.dumps(parsed, ensure_ascii=False, sort_keys=True),
            parsed_output=result,
        ),
    )
    try:
        server.TASK_STORE.transition(
            task_id,
            expected_statuses={TaskStatus.PROCESSING},
            expected_active_run_id=run_id,
            ocr_context=OcrPrintedContext(
                printed_question_no=result.get("printed_question_no"),
                printed_chapter=result.get("printed_chapter"),
            ),
        )
    except StateConflict:
        # A cancelled or replaced run must not attach stale OCR observations.
        pass
    with _OCR_RESULT_LOCK:
        _OCR_RESULTS[cache_key] = deepcopy(result)
        _OCR_RESULTS.move_to_end(cache_key)
        while len(_OCR_RESULTS) > _OCR_RESULT_LIMIT:
            _OCR_RESULTS.popitem(last=False)
    return result


__all__ = ["OCR_ENDPOINT", "OcrProviderError", "clear_ocr_run_model_resolver", "clear_ocr_vault", "close_ocr_client", "configure_ocr_run_model_resolver", "configure_ocr_vault", "ocr_image", "ocr_vault_is_configured"]
