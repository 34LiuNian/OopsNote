from __future__ import annotations

import json
import logging
import base64
import time
import os
from pathlib import Path
from typing import Any, Callable
import re

from pydantic import BaseModel

from openai import OpenAI
from openai import OpenAIError

from app.models import ProblemBlock, TaggingResult

from .base import AIClient
from app.request_context import get_request_id
from app.trace import trace_event
from app.llm_logging import append_llm_error_log, log_raw_output, should_log_raw_output, truncate_preview, truncate_raw

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_PROMPT_CACHE: dict[str, str] = {}


def _load_prompt(filename: str) -> str:
    cached = _PROMPT_CACHE.get(filename)
    if cached is not None:
        return cached
    text = (_PROMPT_DIR / filename).read_text(encoding="utf-8")
    _PROMPT_CACHE[filename] = text
    return text


class OpenAIClient(AIClient):
    """Production-ready AI client backed by OpenAI chat-completions."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        if max_tokens is None:
            env_max = os.getenv("OPENAI_MAX_TOKENS")
            if env_max is not None:
                try:
                    max_tokens = int(env_max)
                except ValueError:
                    max_tokens = None
        self.max_tokens = max_tokens if max_tokens is not None else 900
        self._client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def generate_solution(
        self,
        subject: str,
        problem: ProblemBlock,
        on_delta: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        system_prompt = _load_prompt("solution_system.txt").strip()
        user_prompt = self._format_problem_prompt(subject, problem)
        payload = self._complete_json(
            system_prompt,
            user_prompt + "\n" + _load_prompt("solution_user_suffix.txt").strip(),
            on_delta=on_delta,
        )
        return payload.get("answer", ""), payload.get("explanation", "")

    def classify_problem(self, subject: str, problem: ProblemBlock) -> TaggingResult:
        system_prompt = _load_prompt("tagging_system.txt").strip()
        user_prompt = self._format_problem_prompt(subject, problem)
        payload = self._complete_json(
            system_prompt,
            user_prompt + "\n" + _load_prompt("tagging_user_suffix.txt").strip(),
        )
        return TaggingResult(
            problem_id=problem.problem_id,
            knowledge_points=_ensure_list(payload.get("knowledge_points"), fallback=["未标注"]),
            question_type=str(payload.get("question_type", "解答题")),
            skills=_ensure_list(payload.get("skills"), fallback=["分析推理"]),
            error_hypothesis=_ensure_list(payload.get("error_hypothesis"), fallback=["知识点不熟"]),
            recommended_actions=_ensure_list(
                payload.get("recommended_actions"), fallback=["回顾笔记", "完成 2 道同类题"]
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
        """Generic JSON-producing chat helper for agent-style prompts."""
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
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
        messages = [
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
        messages = [
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
        _ = thinking
        started = time.perf_counter()
        has_image = any(
            isinstance(m.get("content"), list)
            and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m.get("content", []))
            for m in messages
            if isinstance(m, dict)
        )
        approx_chars = 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                approx_chars += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        approx_chars += len(part["text"])
        logger.info(
            "OpenAI request rid=%s model=%s has_image=%s approx_chars=%s",
            get_request_id(),
            self.model,
            has_image,
            approx_chars,
        )
        trace_event(
            "llm_request",
            provider="openai",
            model=self.model,
            has_image=has_image,
            approx_chars=approx_chars,
            max_tokens=self.max_tokens,
            response_format="none",
        )

        response_format_candidates: list[dict[str, Any] | None] = []
        model_name = (self.model or "").lower()
        use_json_object = model_name.startswith("zhipu:") or model_name.startswith("glm-") or ":glm-" in model_name
        # Temporarily disable response_format (json_schema/json_object) for gateway compatibility.
        response_format_candidates.append(None)

        debug_payload = os.getenv("AI_DEBUG_LLM_PAYLOAD", "false").lower() == "true"
        include_image_payload = os.getenv("AI_DEBUG_LLM_PAYLOAD_INCLUDE_IMAGE", "false").lower() == "true"
        if debug_payload:
            try:
                def _redact_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
                    redacted: list[dict[str, Any]] = []
                    for m in msgs:
                        if not isinstance(m, dict):
                            redacted.append(m)
                            continue
                        content = m.get("content")
                        if isinstance(content, list):
                            new_parts = []
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "image_url":
                                    if include_image_payload:
                                        new_parts.append(part)
                                    else:
                                        image_url = part.get("image_url")
                                        url_value = ""
                                        if isinstance(image_url, dict):
                                            url_value = str(image_url.get("url", ""))
                                        elif isinstance(image_url, str):
                                            url_value = image_url
                                        new_parts.append(
                                            {
                                                "type": "image_url",
                                                "image_url": "<omitted>",
                                                "image_url_len": len(url_value),
                                            }
                                        )
                                else:
                                    new_parts.append(part)
                            redacted.append({**m, "content": new_parts})
                        else:
                            redacted.append(m)
                    return redacted

                payload_log_path = os.getenv("AI_DEBUG_LLM_PAYLOAD_PATH")
                if not payload_log_path:
                    payload_log_path = str(Path(__file__).resolve().parents[2] / "storage" / "llm_payloads.log")
                payload_record = {
                    "request_id": get_request_id(),
                    "model": self.model,
                    "response_format": response_format_candidates[0],
                    "messages": _redact_messages(messages),
                    "include_image": include_image_payload,
                }
                with open(payload_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload_record, ensure_ascii=False) + "\n")
            except Exception:
                pass

        def _call_once(*, model: str, msg_payload: list[dict[str, Any]], rf: dict[str, Any] | None):
            if on_delta is None:
                if rf is None:
                    return self._client.chat.completions.create(
                        model=model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        messages=msg_payload,
                    )
                return self._client.chat.completions.create(
                    model=model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=msg_payload,
                    response_format=rf,
                )

            if rf is None:
                chunks = self._client.chat.completions.create(
                    model=model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=msg_payload,
                    stream=True,
                )
            else:
                chunks = self._client.chat.completions.create(
                    model=model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=msg_payload,
                    response_format=rf,
                    stream=True,
                )
            parts: list[str] = []
            finish_reason = None
            suppress_ws = os.getenv("AI_STREAM_SUPPRESS_WHITESPACE", "false").lower() == "true"
            whitespace_run = 0
            for chunk in chunks:
                try:
                    choice = chunk.choices[0]
                    finish_reason = getattr(choice, "finish_reason", finish_reason)
                    delta = getattr(choice.delta, "content", None)
                    if delta:
                        parts.append(delta)
                        if not suppress_ws:
                            try:
                                on_delta(delta)
                            except Exception:
                                pass
                        else:
                            # Prevent UI spam when models emit long runs of whitespace/newlines.
                            # Still keep the raw text for downstream JSON repair.
                            is_ws_only = (delta.strip() == "")
                            if is_ws_only:
                                whitespace_run += len(delta)
                            else:
                                whitespace_run = 0

                            # Allow some whitespace (formatting), but stop forwarding after a while.
                            if (not is_ws_only) or whitespace_run <= 64:
                                try:
                                    on_delta(delta)
                                except Exception:
                                    pass
                except Exception:
                    continue

            class _Msg:
                def __init__(self, content: str) -> None:
                    self.content = content

            class _Choice:
                def __init__(self, content: str, fr) -> None:
                    self.message = _Msg(content)
                    self.finish_reason = fr

            class _Resp:
                def __init__(self, content: str, fr) -> None:
                    self.choices = [_Choice(content, fr)]

            return _Resp("".join(parts), finish_reason)

        last_exc: Exception | None = None
        response = None
        selected_rf: dict[str, Any] | None = None
        for rf in response_format_candidates:
            try:
                response = _call_once(model=self.model, msg_payload=messages, rf=rf)
                content = response.choices[0].message.content or ""
                if (
                    rf is not None
                    and use_json_object
                    and has_image
                    and response_model is not None
                    and content.strip() == ""
                ):
                    logger.warning(
                        "OpenAI gateway returned empty content; retry without response_format rid=%s model=%s",
                        get_request_id(),
                        self.model,
                    )
                    continue
                selected_rf = rf
                break
            except OpenAIError as exc:
                last_exc = exc

                # 1) If the gateway rejected json_schema, try json_object.
                if isinstance(rf, dict) and rf.get("type") == "json_schema":
                    logger.error(
                        "OpenAI gateway rejected json_schema rid=%s model=%s err=%s",
                        get_request_id(),
                        self.model,
                        exc,
                    )
                    # Try json_object fallback if available.
                    continue

                # 2) Some OpenAI-compatible gateways reject the image_url payload shape.
                if has_image and _is_messages_illegal_error(exc):
                    try:
                        rewritten = _rewrite_image_url_messages(messages)
                        logger.warning(
                            "OpenAI gateway rejected messages; retry with rewritten image_url rid=%s model=%s",
                            get_request_id(),
                            self.model,
                        )
                        response = _call_once(model=self.model, msg_payload=rewritten, rf=rf)
                        break
                    except OpenAIError as exc2:
                        last_exc = exc2

                # 3) If configured model is not available in provider, pick a fallback model.
                fallback_model = _pick_fallback_model(current_model=self.model, has_image=has_image, exc=exc)
                if fallback_model and fallback_model != self.model:
                    try:
                        logger.warning(
                            "Model not available; retry with fallback rid=%s model=%s -> %s",
                            get_request_id(),
                            self.model,
                            fallback_model,
                        )
                        response = _call_once(model=fallback_model, msg_payload=messages, rf=rf)
                        break
                    except OpenAIError as exc2:
                        last_exc = exc2

                logger.error("OpenAI chat.completions failed: %s", last_exc)
                raise RuntimeError("OpenAI request failed") from last_exc

        if response is None:
            raise RuntimeError("OpenAI request failed") from last_exc

        finish_reason = getattr(response.choices[0], "finish_reason", None)

        content = response.choices[0].message.content or ""
        if should_log_raw_output():
            log_raw_output(
                {
                    "rid": get_request_id(),
                    "event": "raw_model_output",
                    "provider": "openai",
                    "model": self.model,
                    "has_image": has_image,
                    "finish_reason": finish_reason,
                    "response_format": selected_rf,
                    "response_len": len(content),
                    "response_content": truncate_raw(content),
                }
            )
        if on_delta is not None and should_log_raw_output():
            try:
                on_delta(
                    json.dumps(
                        {
                            "stage": "llm",
                            "event": "raw_output",
                            "provider": "openai",
                            "model": self.model,
                            "finish_reason": finish_reason,
                            "response_format": selected_rf,
                            "response_len": len(content),
                            "response_content": truncate_raw(content),
                        },
                        ensure_ascii=False,
                    )
                )
            except Exception:
                pass
        try:
            data = _parse_json_block(content)
        except ValueError:
            if isinstance(selected_rf, dict) and selected_rf.get("type") == "json_schema":
                preview = truncate_preview(content)
                logger.error(
                    "OpenAI completion did not return JSON for schema rid=%s model=%s: %s",
                    get_request_id(),
                    self.model,
                    preview,
                )
                append_llm_error_log(
                    {
                        "rid": get_request_id(),
                        "event": "schema_json_parse_failed",
                        "provider": "openai",
                        "model": self.model,
                        "has_image": has_image,
                        "finish_reason": finish_reason,
                        "response_format": selected_rf,
                        "response_len": len(content),
                        "response_preview": preview,
                    }
                )
                raise RuntimeError("Model output is not JSON for schema request")
            fallback_keys: list[str] = [
                "answer",
                "explanation",
                "short_answer",
                "verdict",
                "notes",
                "question_type",
            ]
            if response_model is not None:
                try:
                    model_keys = list(getattr(response_model, "model_fields", {}).keys())
                    for k in model_keys:
                        if k not in fallback_keys:
                            fallback_keys.insert(0, str(k))
                except Exception:
                    pass
            extracted, incomplete = _extract_lenient_top_level_string_fields_with_meta(
                content,
                keys=tuple(fallback_keys),
            )
            if extracted:
                if incomplete:
                    logger.warning(
                        "OpenAI completion was not JSON; using lenient extraction rid=%s model=%s keys=%s incomplete=%s finish_reason=%s",
                        get_request_id(),
                        self.model,
                        sorted(extracted.keys()),
                        sorted(incomplete),
                        finish_reason,
                    )
                else:
                    logger.info(
                        "OpenAI completion was not JSON; lenient extraction succeeded rid=%s model=%s keys=%s finish_reason=%s",
                        get_request_id(),
                        self.model,
                        sorted(extracted.keys()),
                        finish_reason,
                    )
                data = extracted
            else:
                logger.error(
                    "OpenAI completion did not return JSON rid=%s (model=%s): %s",
                    get_request_id(),
                    self.model,
                    content,
                )
                # Final fallback so upstream pipeline does not 500.
                data = {
                    "answer": content,
                    "explanation": "",
                    "short_answer": "",
                }

        if response_model is not None:
            try:
                validated = response_model.model_validate(data)
                data = validated.model_dump()
            except Exception as exc:
                logger.error(
                    "OpenAI completion failed schema validation rid=%s model=%s err=%s",
                    get_request_id(),
                    self.model,
                    exc,
                )
                append_llm_error_log(
                    {
                        "rid": get_request_id(),
                        "event": "schema_validation_failed",
                        "provider": "openai",
                        "model": self.model,
                        "has_image": has_image,
                        "finish_reason": finish_reason,
                        "response_format": selected_rf,
                        "error": str(exc),
                        "response_len": len(content),
                        "response_preview": truncate_preview(content),
                        "keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
                    }
                )
                raise RuntimeError("Model output did not match schema") from exc

        trace_event(
            "llm_response",
            provider="openai",
            model=self.model,
            ok=isinstance(data, dict) and bool(data),
            keys=sorted(list(data.keys())) if isinstance(data, dict) else [],
            raw_text=content,
            finish_reason=finish_reason,
        )

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("OpenAI response ok model=%s ms=%.1f", self.model, elapsed_ms)
        return data

    @staticmethod
    def _format_problem_prompt(subject: str, problem: ProblemBlock) -> str:
        latex = "\n".join(problem.latex_blocks)
        return (
            f"学科: {subject}\n"
            f"题干: {problem.problem_text}\n"
            f"Latex: {latex if latex else 'N/A'}"
        )


def _is_messages_illegal_error(exc: OpenAIError) -> bool:
    msg = str(exc)
    return "\"messages\"" in msg and "illegal" in msg


def _rewrite_image_url_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Best-effort normalize image_url part for OpenAI-compatible gateways.

    Some gateways reject the OpenAI-style object form: {image_url: {url: ...}}.
    We retry with the simpler form: {image_url: "data:..."}.
    """

    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        content = m.get("content")
        if not isinstance(content, list):
            out.append(m)
            continue
        new_parts: list[Any] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                new_parts.append(part)
                continue
            image_url = part.get("image_url")
            if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
                new_parts.append({"type": "image_url", "image_url": image_url["url"]})
            else:
                new_parts.append(part)
        out.append({**m, "content": new_parts})
    return out


def _apply_provider_prefix(current_model: str, candidate: str) -> str:
    """Ensure model name matches gateway expected format.

    Some OpenAI-compatible gateways require model format: 'provider:model_id'.
    Error messages often list available models without the provider prefix.
    """

    if ":" in candidate:
        return candidate
    if ":" not in current_model:
        return candidate
    provider = current_model.split(":", 1)[0].strip()
    if not provider:
        return candidate
    return f"{provider}:{candidate}"


def _pick_fallback_model(*, current_model: str, has_image: bool, exc: OpenAIError) -> str | None:
    """Try to extract a usable model from a model_not_available error message."""

    msg = str(exc)
    if "model_not_available" not in msg and "not available" not in msg:
        return None

    m = re.search(r"Available models:\s*(.+?)\s*\}?$", msg)
    if not m:
        return None

    raw = m.group(1)
    candidates = [s.strip() for s in raw.split(",") if s.strip()]
    if not candidates:
        return None

    def _is_vision(name: str) -> bool:
        n = name.lower()
        return "vl" in n or "vision" in n or "4.6v" in n

    def _is_embedding(name: str) -> bool:
        n = name.lower()
        return "bge" in n or "embedding" in n

    if has_image:
        for preferred in [
            "Qwen/Qwen3-VL-32B-Thinking",
            "Qwen/Qwen3-VL-8B-Thinking",
            "zai-org/GLM-4.6V",
        ]:
            for c in candidates:
                if c == preferred:
                    return _apply_provider_prefix(current_model, c)
        for c in candidates:
            if _is_vision(c):
                return _apply_provider_prefix(current_model, c)
        return _apply_provider_prefix(current_model, candidates[0])

    # text-only
    for preferred in [
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3.2",
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen3-8B",
    ]:
        for c in candidates:
            if c == preferred:
                return _apply_provider_prefix(current_model, c)
    for c in candidates:
        if (not _is_vision(c)) and (not _is_embedding(c)):
            return _apply_provider_prefix(current_model, c)
    return _apply_provider_prefix(current_model, candidates[0])


def _parse_json_block(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("JSON braces not found")

    # Prefer raw_decode to correctly stop at the end of the first JSON object
    # and ignore any trailing text. This also avoids brace-matching issues
    # when the model includes LaTeX containing many '{' / '}' inside strings.
    decoder = json.JSONDecoder()
    candidate = text[start:]
    try:
        obj, _end = decoder.raw_decode(candidate)
        if not isinstance(obj, dict):
            raise ValueError("JSON root was not an object")
        return obj
    except json.JSONDecodeError as exc:
        # Common model failures:
        # - Invalid backslash escapes inside strings (e.g. "\(a\)")
        # - Unescaped control chars inside strings (literal newlines/tabs)
        logger.info("OpenAI JSON repair triggered rid=%s", get_request_id())

        repaired = _repair_invalid_string_escapes(candidate)
        repaired = _strip_disallowed_control_chars_outside_strings(repaired)
        repaired = _remove_trailing_commas(repaired)
        repaired = _balance_unclosed_json_brackets(repaired)
        try:
            obj, _end = decoder.raw_decode(repaired)
        except json.JSONDecodeError as exc2:
            # Some gateways return *truncated* JSON (e.g., cut mid-string). Attempt a
            # best-effort extraction of common top-level string fields so /upload doesn't 500.
            extracted, incomplete = _extract_lenient_top_level_string_fields_with_meta(
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
                if incomplete:
                    logger.warning(
                        "OpenAI JSON was not parseable; using lenient extraction rid=%s keys=%s incomplete=%s",
                        get_request_id(),
                        sorted(extracted.keys()),
                        sorted(incomplete),
                    )
                else:
                    logger.info(
                        "OpenAI JSON was not parseable; lenient extraction succeeded rid=%s keys=%s",
                        get_request_id(),
                        sorted(extracted.keys()),
                    )
                return extracted

            _log_json_decode_error("OpenAI", candidate, exc, repaired, exc2)
            raise

        if not isinstance(obj, dict):
            raise ValueError("JSON root was not an object")
        return obj


_TOP_LEVEL_STRING_KEY_RE = re.compile(r'"(?P<key>[^"]+)"\s*:\s*"')


def _extract_lenient_top_level_string_fields(snippet: str, keys: tuple[str, ...]) -> dict[str, Any]:
    payload, _incomplete = _extract_lenient_top_level_string_fields_with_meta(snippet, keys)
    return payload


def _extract_lenient_top_level_string_fields_with_meta(
    snippet: str,
    keys: tuple[str, ...],
) -> tuple[dict[str, Any], list[str]]:
    # Only attempts to extract string values of known keys.
    wanted = set(keys)
    out: dict[str, Any] = {}
    incomplete: list[str] = []
    for match in _TOP_LEVEL_STRING_KEY_RE.finditer(snippet):
        key = match.group("key")
        if key not in wanted or key in out:
            continue
        value, _end, closed = _parse_json_string_lenient(snippet, match.end() - 1)
        out[key] = value
        if not closed:
            incomplete.append(key)

    # Fallback: direct search per key (helps when regex misses due to odd characters)
    for key in keys:
        if key in out:
            continue
        needle = f'"{key}"'
        idx = snippet.find(needle)
        if idx == -1:
            continue
        colon = snippet.find(":", idx + len(needle))
        if colon == -1:
            continue
        q = snippet.find('"', colon)
        if q == -1:
            continue
        value, _end, closed = _parse_json_string_lenient(snippet, q)
        out[key] = value
        if not closed:
            incomplete.append(key)

    return out, incomplete


def _parse_json_string_lenient(s: str, start_quote_index: int) -> tuple[str, int, bool]:
    """Parse a JSON string starting at the opening quote.

    If the string is truncated (EOF before closing quote), returns what we have.
    """

    if start_quote_index < 0 or start_quote_index >= len(s) or s[start_quote_index] != '"':
        return "", start_quote_index, True

    out_chars: list[str] = []
    i = start_quote_index + 1
    while i < len(s):
        ch = s[i]
        if ch == '"':
            return "".join(out_chars), i + 1, True
        if ch == "\\":
            if i + 1 >= len(s):
                # Truncated escape.
                return "".join(out_chars), len(s), False
            nxt = s[i + 1]
            if nxt in ('"', "\\", "/"):
                out_chars.append(nxt)
                i += 2
                continue
            if nxt == "b":
                out_chars.append("\b")
                i += 2
                continue
            if nxt == "f":
                out_chars.append("\f")
                i += 2
                continue
            if nxt == "n":
                out_chars.append("\n")
                i += 2
                continue
            if nxt == "r":
                out_chars.append("\r")
                i += 2
                continue
            if nxt == "t":
                out_chars.append("\t")
                i += 2
                continue
            if nxt == "u":
                hex_part = s[i + 2 : i + 6]
                if len(hex_part) == 4 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    out_chars.append(chr(int(hex_part, 16)))
                    i += 6
                    continue
                # Malformed unicode escape: keep literally.
                out_chars.append("\\u")
                i += 2
                continue
            # Unknown escape: keep literally.
            out_chars.append(nxt)
            i += 2
            continue

        # Allow literal newlines etc (some gateways violate JSON rules).
        out_chars.append(ch)
        i += 1

    return "".join(out_chars), len(s), False


def _log_json_decode_error(
    label: str,
    original: str,
    original_exc: json.JSONDecodeError,
    repaired: str,
    repaired_exc: json.JSONDecodeError,
) -> None:
    def _slice_around(s: str, pos: int, radius: int = 120) -> str:
        lo = max(0, pos - radius)
        hi = min(len(s), pos + radius)
        return s[lo:hi]

    logger.error(
        "%s JSON parse failed even after repair rid=%s. original=(line=%s col=%s pos=%s msg=%s) repaired=(line=%s col=%s pos=%s msg=%s) original_around=%r repaired_around=%r",
        label,
        get_request_id(),
        original_exc.lineno,
        original_exc.colno,
        original_exc.pos,
        original_exc.msg,
        repaired_exc.lineno,
        repaired_exc.colno,
        repaired_exc.pos,
        repaired_exc.msg,
        _slice_around(original, original_exc.pos),
        _slice_around(repaired, repaired_exc.pos),
    )


def _repair_invalid_string_escapes(snippet: str) -> str:
    """Repair invalid backslash escapes inside JSON string literals.

    Only modifies backslashes *within* double-quoted strings.
    If a backslash is not followed by a valid JSON escape char, it is doubled.
    """

    out: list[str] = []
    in_string = False
    i = 0
    while i < len(snippet):
        ch = snippet[i]

        if in_string and ch in ("\n", "\r", "\t"):
            # JSON does not allow literal control characters inside strings.
            # Convert them into escaped sequences.
            if ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            else:
                out.append("\\t")
            i += 1
            continue

        if in_string and isinstance(ch, str) and ch and ord(ch) < 0x20:
            # Other control chars: escape as unicode.
            out.append(f"\\u{ord(ch):04x}")
            i += 1
            continue

        if ch == '"':
            # Toggle string state if quote is not escaped.
            backslashes = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
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
            # Some providers return JSON strings containing LaTeX with single backslashes
            # like "\frac". In JSON, "\f" is a valid escape (form-feed), which would
            # silently corrupt the payload rather than raising. If an escape letter is
            # followed by an alphabetic char, treat it as LaTeX and preserve the backslash.
            if nxt in ("b", "f", "n", "r", "t") and i + 2 < len(snippet) and snippet[i + 2].isalpha():
                out.append("\\\\")
                i += 1
                continue

            if nxt in ('"', "\\", "/", "b", "f", "n", "r", "t"):
                out.append("\\" + nxt)
                i += 2
                continue

            if nxt == "u":
                # Keep unicode escape as-is (even if malformed; json.loads will still fail).
                out.append("\\u")
                i += 2
                continue

            # Invalid escape sequence: double the backslash.
            out.append("\\\\")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _strip_disallowed_control_chars_outside_strings(snippet: str) -> str:
    """Remove control characters that JSON does not permit as whitespace.

    JSON allows only space, tab, CR, and LF as whitespace outside strings.
    Some gateways can leak other control chars (e.g., form-feed) via decoding.
    """

    out: list[str] = []
    in_string = False
    i = 0
    while i < len(snippet):
        ch = snippet[i]

        if ch == '"':
            backslashes = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                in_string = not in_string
            out.append(ch)
            i += 1
            continue

        if not in_string:
            # JSON allows only space, tab, CR, and LF as whitespace.
            # Normalize any other unicode whitespace (e.g., NBSP, ideographic space)
            # to a regular space to keep the parser happy.
            if ch.isspace() and ch not in ("\t", "\n", "\r", " "):
                out.append(" ")
                i += 1
                continue

            if ord(ch) < 0x20 and ch not in ("\t", "\n", "\r", " "):
                # Drop disallowed control chars outside strings.
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _remove_trailing_commas(snippet: str) -> str:
    """Remove trailing commas before '}' or ']' outside strings."""

    out: list[str] = []
    in_string = False
    i = 0
    while i < len(snippet):
        ch = snippet[i]

        if ch == '"':
            backslashes = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
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
    """Best-effort fix for responses missing closing '}' / ']'.

    Some OpenAI-compatible gateways occasionally emit JSON that is otherwise well-formed
    but missing the final closing brace/bracket. We balance bracket pairs *outside* of
    strings and append any missing closing delimiters.

    This is intentionally conservative: it does not attempt to reorder tokens, only to
    close what was opened.
    """

    if not snippet:
        return snippet

    stack: list[str] = []
    in_string = False
    i = 0
    while i < len(snippet):
        ch = snippet[i]

        if ch == '"':
            backslashes = 0
            j = i - 1
            while j >= 0 and snippet[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                in_string = not in_string
            i += 1
            continue

        if in_string:
            # Skip escaped quotes/backslashes handling via the backslash count above.
            i += 1
            continue

        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch == "}":
            if stack and stack[-1] == "}":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "]":
                stack.pop()

        i += 1

    if not stack:
        return snippet

    return snippet + "".join(reversed(stack))


def _ensure_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return fallback
