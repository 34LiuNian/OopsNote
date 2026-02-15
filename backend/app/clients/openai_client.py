from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from app.models import ProblemBlock, TaggingResult

from .base import AIClient

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_PROMPT_CACHE: dict[str, str] = {}


def _load_prompt(filename: str) -> str:
    """读取并缓存提示词文件内容。"""
    cached = _PROMPT_CACHE.get(filename)
    if cached is not None:
        return cached
    text = (_PROMPT_DIR / filename).read_text(encoding="utf-8")
    _PROMPT_CACHE[filename] = text
    return text


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

    def generate_solution(
        self,
        subject: str,
        problem: ProblemBlock,
        on_delta: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        """使用解题提示词生成 answer 与 explanation。"""
        system_prompt = _load_prompt("solution_system.txt").strip()
        user_prompt = self._format_problem_prompt(subject, problem)
        payload = self._complete_json(
            system_prompt,
            user_prompt + "\n" + _load_prompt("solution_user_suffix.txt").strip(),
            on_delta=on_delta,
        )
        return str(payload.get("answer", "")), str(payload.get("explanation", ""))

    def classify_problem(self, subject: str, problem: ProblemBlock) -> TaggingResult:
        """使用打标提示词生成结构化标签结果。"""
        system_prompt = _load_prompt("tagging_system.txt").strip()
        user_prompt = self._format_problem_prompt(subject, problem)
        payload = self._complete_json(
            system_prompt,
            user_prompt + "\n" + _load_prompt("tagging_user_suffix.txt").strip(),
        )
        return TaggingResult(
            problem_id=problem.problem_id,
            knowledge_points=_ensure_list(payload.get("knowledge_points"), ["未标注"]),
            question_type=str(payload.get("question_type", "解答题")),
            skills=_ensure_list(payload.get("skills"), ["分析推理"]),
            error_hypothesis=_ensure_list(payload.get("error_hypothesis"), ["知识点不熟"]),
            recommended_actions=_ensure_list(
                payload.get("recommended_actions"), ["回顾笔记", "完成 2 道同类题"]
            ),
        )

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """通用结构化文本对话入口。"""
        return self._complete_json(
            system_prompt,
            user_prompt,
            response_model=response_model,
            on_delta=on_delta,
            thinking=thinking,
        )

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
        return self._complete_json_messages(
            messages,
            response_model=response_model,
            on_delta=on_delta,
            thinking=thinking,
        )

    def _complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """将 system/user 文本包装成 messages 并请求模型。"""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._complete_json_messages(
            messages,
            response_model=response_model,
            on_delta=on_delta,
            thinking=thinking,
        )

    def _complete_json_messages(
        self,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """请求 chat.completions 并将返回文本解析为 JSON 对象。"""
        _ = thinking
        self._log_payload(messages)

        try:
            content = self._call_model(messages, on_delta=on_delta)
        except OpenAIError as exc:
            raise RuntimeError("OpenAI request failed") from exc

        try:
            data = _parse_json_block(content)
        except ValueError as exc:
            raise RuntimeError("Model output is not JSON") from exc

        if response_model is not None:
            data = _trim_payload_for_model(data, response_model)
            data = response_model.model_validate(data).model_dump()
        return data

    def _call_model(
        self,
        messages: list[dict[str, Any]],
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """调用 OpenAI chat.completions，支持流式与非流式两种模式。"""
        if on_delta is None:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=messages,
            )
            return str(response.choices[0].message.content or "")

        chunks = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=messages,
            stream=True,
        )
        parts: list[str] = []
        for chunk in chunks:
            try:
                delta = getattr(chunk.choices[0].delta, "content", None)
            except Exception:
                delta = None
            if not delta:
                continue
            parts.append(delta)
            try:
                on_delta(delta)
            except Exception:
                pass
        return "".join(parts)

    def _log_payload(self, messages: list[dict[str, Any]]) -> None:
        """按调试开关记录请求 payload，默认隐藏图片 data URL。"""
        if os.getenv("AI_DEBUG_LLM_PAYLOAD", "false").lower() != "true":
            return

        include_image = (
            os.getenv("AI_DEBUG_LLM_PAYLOAD_INCLUDE_IMAGE", "false").lower() == "true"
        )

        def _redact(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
            redacted: list[dict[str, Any]] = []
            for m in msgs:
                content = m.get("content") if isinstance(m, dict) else None
                if not isinstance(content, list):
                    redacted.append(m)
                    continue
                parts: list[Any] = []
                for part in content:
                    if not isinstance(part, dict) or part.get("type") != "image_url":
                        parts.append(part)
                        continue
                    if include_image:
                        parts.append(part)
                        continue
                    url = ""
                    image_url = part.get("image_url")
                    if isinstance(image_url, dict):
                        url = str(image_url.get("url", ""))
                    elif isinstance(image_url, str):
                        url = image_url
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": "<omitted>",
                            "image_url_len": len(url),
                        }
                    )
                redacted.append({**m, "content": parts})
            return redacted

        payload_path = os.getenv("AI_DEBUG_LLM_PAYLOAD_PATH")
        if not payload_path:
            payload_path = str(Path(__file__).resolve().parents[2] / "storage" / "llm_payloads.log")

        record = {
            "request_id": "-",
            "model": self.model,
            "response_format": None,
            "messages": _redact(messages),
            "include_image": include_image,
        }
        try:
            with open(payload_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("failed to write llm payload log")

    @staticmethod
    def _format_problem_prompt(subject: str, problem: ProblemBlock) -> str:
        """把题目对象拼装为标准文本提示。"""
        latex = "\n".join(problem.latex_blocks)
        return (
            f"学科: {subject}\n"
            f"题干: {problem.problem_text}\n"
            f"Latex: {latex if latex else 'N/A'}"
        )


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


def _ensure_list(value: Any, fallback: list[str]) -> list[str]:
    """将值归一化为字符串列表，缺失时使用 fallback。"""
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return fallback


def _trim_payload_for_model(
    payload: dict[str, Any],
    response_model: type[BaseModel],
) -> dict[str, Any]:
    """按 response_model 字段白名单裁剪 payload，避免额外字段触发校验失败。"""
    model_fields = getattr(response_model, "model_fields", {})
    if not isinstance(payload, dict) or not model_fields:
        return payload
    allowed = set(model_fields.keys())
    return {key: value for key, value in payload.items() if key in allowed}
