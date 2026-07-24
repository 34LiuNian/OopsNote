"""OCR tool shared by restricted managed-worker transports."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx


MAX_IMAGE_BYTES = 12 * 1024 * 1024
OCR_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
OCR_INSTRUCTION = (
    "Extract only printed question content. Return one strict JSON object: "
    "{content_format:'oopsmark-v1', subject:'math|physics|chemistry', "
    "question_type:'单选题|多选题|填空题|解答题', problem_text:string, "
    "options:string[], has_diagram:boolean, uncertain_regions:string[], "
    "confidence:number}. Use OopsMark v1: inline math is $...$, display math "
    "is $$...$$, options never appear in problem_text, and never emit raw LaTeX "
    "environments such as array, tabular, enumerate, or tikzpicture. Do not solve "
    "or invent unreadable text."
)


def _load_ocr_config() -> dict[str, Any]:
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


def ocr_image(path: str) -> dict[str, Any]:
    """Extract one managed task image into strict OopsMark-oriented OCR JSON."""
    image_path = Path(path).expanduser().resolve()
    mime, _ = mimetypes.guess_type(image_path.name)
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError("Unsupported OCR image type")
    try:
        image = image_path.read_bytes()
    except OSError as error:
        raise ValueError(f"OCR image cannot be read: {image_path}") from error
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("OCR image exceeds 12 MiB limit")

    config = _load_ocr_config()
    api_key = str(config.get("dashscope_api_key") or "")
    model = str(config.get("model") or "")
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
        response = httpx.post(
            OCR_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("DashScope OCR request or response failed") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("DashScope OCR returned a non-object result")
    return parsed
