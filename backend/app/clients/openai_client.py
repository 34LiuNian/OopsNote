from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI, OpenAIError

from .base import AIClient

logger = logging.getLogger(__name__)


class OpenAIClient(AIClient):
    """最小化 OpenAI 客户端：只做基础请求、流式拼接和 JSON 解析。"""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int | None = None,
        debug_payload: bool = False,
        debug_payload_path: str | None = None,
    ) -> None:
        """初始化客户端与基础推理参数。"""
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.debug_payload = debug_payload
        self.debug_payload_path = debug_payload_path
        if max_tokens is None:
            env_max = os.getenv("OPENAI_MAX_TOKENS")
            if env_max:
                try:
                    max_tokens = int(env_max)
                except ValueError:
                    max_tokens = None
        self.max_tokens = max_tokens if max_tokens is not None else 100000
        self._client = (
            OpenAI(api_key=api_key, base_url=base_url)
            if base_url
            else OpenAI(api_key=api_key)
        )

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """通用结构化文本对话入口。"""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._complete_json(messages, thinking=thinking)

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """通用结构化图文对话入口。"""
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        return self._complete_json(messages, thinking=thinking)

    def _complete_json(
        self,
        messages: list[dict[str, Any]],
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """请求 chat.completions 并将返回文本解析为 JSON 对象。"""
        content = self._call_model(messages, thinking=thinking)
        return _parse_json_block(content)

    def _call_model(
        self,
        messages: list[dict[str, Any]],
        thinking: bool | None = None,
    ) -> str:
        """调用 OpenAI chat.completions，仅支持非流式。"""
        # Some models or gateways are picky about 'system' role in vision tasks.
        # We also want to merge prompts into a single user message if desirable.
        has_image = any(
            isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
            for m in messages
        )

        final_messages = messages
        if has_image:
            # For vision models, some gateways/models (like GLM-V or older GPT-4V APIs)
            # prefer system prompt merged into user prompt.
            system_msgs = [m for m in messages if m["role"] == "system"]
            user_msgs = [m for m in messages if m["role"] == "user"]
            if system_msgs and user_msgs:
                system_content = "\n".join([str(m["content"]) for m in system_msgs])
                # We assume the first user message is the one to prepend to.
                user_content = user_msgs[0]["content"]
                if isinstance(user_content, list):
                    # For multi-modal content, find the first text block to prepend to
                    text_found = False
                    for part in user_content:
                        if part.get("type") == "text":
                            part["text"] = f"{system_content}\n\n{part['text']}"
                            text_found = True
                            break
                    if not text_found:
                        user_content.insert(0, {"type": "text", "text": system_content})
                else:
                    user_msgs[0]["content"] = f"{system_content}\n\n{user_content}"
                
                # Remove system messages
                final_messages = [m for m in messages if m["role"] != "system"]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": final_messages,
        }

        # SiliconFlow thinking mode (only if model name contains thinking or instructed)
        if thinking:
            # Use extra_body for SiliconFlow-style thinking
            kwargs["extra_body"] = {"enable_thinking": True}

        # JSON Mode support - be conservative
        if "gpt-4" in self.model or "gpt-3.5" in self.model:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
            content = str(response.choices[0].message.content or "")
            finish_reason = response.choices[0].finish_reason
            usage = response.usage.model_dump() if response.usage else {}

            if self.debug_payload:
                self._write_payload_log(
                    messages=final_messages,
                    response_text=content,
                    finish_reason=finish_reason,
                    usage=usage,
                    thinking=thinking,
                )
            return content
        except Exception as e:
            err_msg = str(e)
            # Fallback for thinking mode if it fails
            if "extra_body" in kwargs and ("enable_thinking" in err_msg or "extra_body" in err_msg or "400" in err_msg):
                logger.warning("Model/Gateway failed with thinking mode, falling back to standard. err=%s", err_msg)
                new_kwargs = {k: v for k, v in kwargs.items() if k != "extra_body"}
                try:
                    response = self._client.chat.completions.create(**new_kwargs)
                    content = str(response.choices[0].message.content or "")
                    finish_reason = response.choices[0].finish_reason
                    usage = response.usage.model_dump() if response.usage else {}
                    if self.debug_payload:
                         self._write_payload_log(
                            messages=final_messages, 
                            response_text=content, 
                            finish_reason=finish_reason,
                            usage=usage,
                            thinking=False
                        )
                    return content
                except Exception as retry_exc:
                    err_msg = f"Standard mode also failed: {str(retry_exc)}"

            if self.debug_payload:
                self._write_payload_log(
                    messages=final_messages,
                    response_text=f"ERROR: {err_msg}",
                    finish_reason="error",
                    thinking=thinking,
                )
            raise 

    def _write_payload_log(
        self,
        messages: list[dict[str, Any]],
        response_text: str,
        finish_reason: str | None = None,
        usage: dict[str, Any] | None = None,
        thinking: bool | None = None,
    ) -> None:
        """记录请求与响应详情到日志文件。"""
        try:
            log_path = self.debug_payload_path
            if not log_path:
                log_path = str(
                    Path(__file__).resolve().parents[2] / "storage" / "llm_payloads.log"
                )

            # 简化消息体，避免过大的图片 base64 撑爆日志
            include_image = (
                os.getenv("AI_DEBUG_LLM_PAYLOAD_INCLUDE_IMAGE", "false").lower()
                == "true"
            )
            logged_messages = []
            for m in messages:
                item = {"role": m.get("role"), "content": m.get("content")}
                if not include_image and isinstance(item["content"], list):
                    item["content"] = [
                        (
                            c
                            if c.get("type") != "image_url"
                            else {
                                "type": "image_url",
                                "image_url": {"url": f"base64_len={len(c['image_url']['url'])}"},
                            }
                        )
                        for c in item["content"]
                    ]
                logged_messages.append(item)

            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
                "base_url": self.base_url,
                "thinking": thinking,
                "finish_reason": finish_reason,
                "usage": usage,
                "messages": logged_messages,
                "response": response_text,
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Failed to write LLM payload log: %s", exc)


def _parse_json_block(text: str) -> dict[str, Any]:
    """从模型文本中提取 第一个 或 最像 的 JSON 对象。"""
    # 0. 预处理：去掉常见的 Markdown 代码块包装
    if "```" in text:
        # 寻找 ```json ... ``` 或 ``` ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # 1. 尝试寻找从前往后第一个 { 和从后往前的最后一个 }
    start = text.find("{")
    if start < 0:
        logger.debug("Raw content for failed JSON search: %s", text)
        raise ValueError("JSON braces not found")
    
    end = text.rfind("}")
    if end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2. 尝试从后往前寻找最后一个能让 json.loads 成功的 { ... } 块
    # 针对思考模型（如 DeepSeek R1），JSON 通常位于输出的最末尾
    for i in range(text.rfind("{"), -1, -1):
        if text[i] == "{":
            snippet = text[i:].strip()
            # 寻找对应的 }
            last_bracket = snippet.rfind("}")
            if last_bracket > 0:
                try:
                    return json.loads(snippet[: last_bracket + 1])
                except json.JSONDecodeError:
                    continue

    # 3. 极简提取方案：针对完全损坏的包裹（如 Markdown 代码块未闭合）
    results = {}
    pattern = r'"(\w+)":\s*"((?:\\.|[^"\\])*)"'
    for match in re.finditer(pattern, text):
        results[match.group(1)] = match.group(2)
    
    if results:
        logger.warning("Standard JSON parsing failed, used regex fallback.")
        return results

    logger.debug("Failed candidate (last 500 chars): %s", text[-500:])
    raise ValueError("Final JSON parse attempt failed")
