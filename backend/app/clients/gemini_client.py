"""Gemini client has been removed.

OopsNote 现在统一通过 OpenAI 协议（含 OpenAI-compatible gateway）访问模型。

本文件仅作为占位，避免历史 import/配置导致难以理解的 ImportError。
如果你仍在配置中写了 provider=gemini，请改为 provider=openai，并设置 BASE_URL 指向你的网关。
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from .base import AIClient


class GeminiClient(AIClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "GeminiClient 已废弃：本项目仅支持 OpenAI 协议。"
            "请使用 provider=openai 并配置 base_url 指向你的网关。"
        )

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("GeminiClient 已废弃")

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
        raise RuntimeError("GeminiClient 已废弃")
