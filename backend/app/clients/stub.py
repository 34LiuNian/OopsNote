from __future__ import annotations

import random
import json
from typing import Any, Callable

from pydantic import BaseModel


class StubAIClient:
    """Deterministic AI client used for local development without API keys."""

    model = "stub-local-v1"

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("StubAIClient: Placeholder functionality is disabled. Please configure a real AI provider.")

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("StubAIClient: Placeholder functionality is disabled. Please configure a real AI provider.")


def _maybe_stream_payload(
    on_delta: Callable[[str], None] | None, payload: dict[str, Any]
) -> None:
    if on_delta is None:
        return
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    for i in range(0, len(text), 12):
        try:
            on_delta(text[i : i + 12])
        except Exception:
            break
