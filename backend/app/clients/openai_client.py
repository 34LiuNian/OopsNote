from __future__ import annotations

import base64
import json
import logging
import os
import re
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
    ) -> None:
        """初始化客户端与基础推理参数。"""
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        if max_tokens is None:
            env_max = os.getenv("OPENAI_MAX_TOKENS")
            if env_max:
                try:
                    max_tokens = int(env_max)
                except ValueError:
                    max_tokens = None
        self.max_tokens = max_tokens if max_tokens is not None else 900
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
        return self._complete_json(messages)

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
        return self._complete_json(messages)

    def _complete_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """请求 chat.completions 并将返回文本解析为 JSON 对象。"""
        try:
            content = self._call_model(messages)
            return _parse_json_block(content)
        except Exception as exc:
            logger.error("LLM request or parsing failed: %s", exc)
            return {}

    def _call_model(
        self,
        messages: list[dict[str, Any]],
    ) -> str:
        """调用 OpenAI chat.completions，仅支持非流式。"""
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=messages,
        )
        return str(response.choices[0].message.content or "")


def _parse_json_block(text: str) -> dict[str, Any]:
    """从模型文本中提取第一个 JSON 对象，失败时做轻量修复。"""
    start = text.find("{")
    if start < 0:
        raise ValueError("JSON braces not found")

    decoder = json.JSONDecoder()
    candidate = text[start:]

    try:
        obj, _ = decoder.raw_decode(candidate)
        if not isinstance(obj, dict):
            raise ValueError("JSON root was not an object")
        return obj
    except json.JSONDecodeError:
        repaired = _repair_invalid_string_escapes(candidate)
        repaired = _strip_disallowed_control_chars_outside_strings(repaired)
        repaired = _remove_trailing_commas(repaired)
        repaired = _balance_unclosed_json_brackets(repaired)

        try:
            obj, _ = decoder.raw_decode(repaired)
            if not isinstance(obj, dict):
                raise ValueError("JSON root was not an object")
            return obj
        except json.JSONDecodeError:
            extracted, _ = _extract_lenient_top_level_string_fields_with_meta(
                repaired,
                keys=(
                    "answer",
                    "explanation",
                    "short_answer",
                    "verdict",
                    "notes",
                    "question_type",
                ),
            )
            if extracted:
                return extracted
            raise


_TOP_LEVEL_STRING_KEY_RE = re.compile(r'"(?P<key>[^"]+)"\s*:\s*"')


def _extract_lenient_top_level_string_fields(
    snippet: str,
    keys: tuple[str, ...],
) -> dict[str, Any]:
    """只提取指定 key 的顶层字符串值（宽松模式）。"""
    payload, _ = _extract_lenient_top_level_string_fields_with_meta(snippet, keys)
    return payload


def _extract_lenient_top_level_string_fields_with_meta(
    snippet: str,
    keys: tuple[str, ...],
) -> tuple[dict[str, Any], list[str]]:
    """宽松提取顶层字符串字段，并返回哪些字段是截断不完整的。"""
    wanted = set(keys)
    out: dict[str, Any] = {}
    incomplete: list[str] = []

    for match in _TOP_LEVEL_STRING_KEY_RE.finditer(snippet):
        key = match.group("key")
        if key not in wanted or key in out:
            continue
        value, _, closed = _parse_json_string_lenient(snippet, match.end() - 1)
        out[key] = value
        if not closed:
            incomplete.append(key)

    for key in keys:
        if key in out:
            continue
        needle = f'"{key}"'
        idx = snippet.find(needle)
        if idx < 0:
            continue
        colon = snippet.find(":", idx + len(needle))
        if colon < 0:
            continue
        quote = snippet.find('"', colon)
        if quote < 0:
            continue
        value, _, closed = _parse_json_string_lenient(snippet, quote)
        out[key] = value
        if not closed:
            incomplete.append(key)

    return out, incomplete


def _parse_json_string_lenient(s: str, start_quote_index: int) -> tuple[str, int, bool]:
    """宽松解析 JSON 字符串，允许截断并返回 closed 标记。"""
    if start_quote_index < 0 or start_quote_index >= len(s) or s[start_quote_index] != '"':
        return "", start_quote_index, True

    out: list[str] = []
    i = start_quote_index + 1
    while i < len(s):
        ch = s[i]
        if ch == '"':
            return "".join(out), i + 1, True
        if ch == "\\":
            if i + 1 >= len(s):
                return "".join(out), len(s), False
            nxt = s[i + 1]
            if nxt in ('"', "\\", "/"):
                out.append(nxt)
                i += 2
                continue
            if nxt == "b":
                out.append("\b")
                i += 2
                continue
            if nxt == "f":
                out.append("\f")
                i += 2
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "r":
                out.append("\r")
                i += 2
                continue
            if nxt == "t":
                out.append("\t")
                i += 2
                continue
            if nxt == "u":
                hex_part = s[i + 2 : i + 6]
                if len(hex_part) == 4 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    out.append(chr(int(hex_part, 16)))
                    i += 6
                    continue
                out.append("\\u")
                i += 2
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1

    return "".join(out), len(s), False


def _repair_invalid_string_escapes(snippet: str) -> str:
    """修复字符串内无效反斜杠转义和字面控制字符。"""
    out: list[str] = []
    in_string = False
    i = 0

    while i < len(snippet):
        ch = snippet[i]

        if in_string and ch in ("\n", "\r", "\t"):
            out.append("\\n" if ch == "\n" else "\\r" if ch == "\r" else "\\t")
            i += 1
            continue

        if in_string and ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
            i += 1
            continue

        if ch == '"':
            slash_count = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                slash_count += 1
                j -= 1
            if slash_count % 2 == 0:
                in_string = not in_string
            out.append(ch)
            i += 1
            continue

        if in_string and ch == "\\":
            if i + 1 >= len(snippet):
                out.append("\\\\")
                i += 1
                continue
            nxt = snippet[i + 1]
            if nxt in ('"', "\\", "/", "b", "f", "n", "r", "t"):
                out.append("\\" + nxt)
                i += 2
                continue
            if nxt == "u":
                out.append("\\u")
                i += 2
                continue
            out.append("\\\\")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _strip_disallowed_control_chars_outside_strings(snippet: str) -> str:
    """移除字符串外不符合 JSON 规范的控制字符。"""
    out: list[str] = []
    in_string = False
    i = 0

    while i < len(snippet):
        ch = snippet[i]
        if ch == '"':
            slash_count = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                slash_count += 1
                j -= 1
            if slash_count % 2 == 0:
                in_string = not in_string
            out.append(ch)
            i += 1
            continue

        if not in_string:
            if ch.isspace() and ch not in (" ", "\t", "\n", "\r"):
                out.append(" ")
                i += 1
                continue
            if ord(ch) < 0x20 and ch not in (" ", "\t", "\n", "\r"):
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _remove_trailing_commas(snippet: str) -> str:
    """移除对象/数组结束前的多余逗号。"""
    out: list[str] = []
    in_string = False
    i = 0

    while i < len(snippet):
        ch = snippet[i]
        if ch == '"':
            slash_count = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                slash_count += 1
                j -= 1
            if slash_count % 2 == 0:
                in_string = not in_string
            out.append(ch)
            i += 1
            continue

        if not in_string and ch == ",":
            j = i + 1
            while j < len(snippet) and snippet[j] in (" ", "\t", "\n", "\r"):
                j += 1
            if j < len(snippet) and snippet[j] in ("]", "}"):
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _balance_unclosed_json_brackets(snippet: str) -> str:
    """为截断 JSON 自动补齐缺失的 ] 或 }。"""
    stack: list[str] = []
    in_string = False
    i = 0

    while i < len(snippet):
        ch = snippet[i]
        if ch == '"':
            slash_count = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                slash_count += 1
                j -= 1
            if slash_count % 2 == 0:
                in_string = not in_string
            i += 1
            continue

        if not in_string:
            if ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch == "}" and stack and stack[-1] == "}":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "]":
                stack.pop()

        i += 1

    if not stack:
        return snippet
    return snippet + "".join(reversed(stack))
