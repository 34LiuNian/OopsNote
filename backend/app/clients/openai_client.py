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
    ) -> dict[str, Any]:
        """Generic JSON-producing chat helper for agent-style prompts."""
        return self._complete_json(system_prompt, user_prompt, response_model=response_model, on_delta=on_delta)

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
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
        return self._complete_json_messages(messages, response_model=response_model, on_delta=on_delta)

    def _complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._complete_json_messages(messages, response_model=response_model, on_delta=on_delta)

    def _complete_json_messages(
        self,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
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
            response_format=(
                "json_schema" if response_model is not None else "json_object"
            ),
        )

        response_format_candidates: list[dict[str, Any]] = []
        if response_model is not None:
            # If the gateway supports it, pass the schema directly (Gemini-like behavior).
            # Many OpenAI-compatible gateways still don't support json_schema; we will
            # automatically fallback to json_object.
            try:
                schema = response_model.model_json_schema()
                response_format_candidates.append(
                    {
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__,
                            "schema": schema,
                            "strict": True,
                        },
                    }
                )
            except Exception:
                # If schema generation fails for any reason, skip it.
                response_format_candidates = []

        response_format_candidates.append({"type": "json_object"})

        last_exc: Exception | None = None
        response = None
        for rf in response_format_candidates:
            try:
                if on_delta is None:
                    response = self._client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        messages=messages,
                        response_format=rf,
                    )
                else:
                    # True streaming: push deltas as they arrive.
                    chunks = self._client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        messages=messages,
                        response_format=rf,
                        stream=True,
                    )
                    parts: list[str] = []
                    finish_reason = None
                    for chunk in chunks:
                        try:
                            choice = chunk.choices[0]
                            finish_reason = getattr(choice, "finish_reason", finish_reason)
                            delta = getattr(choice.delta, "content", None)
                            if delta:
                                parts.append(delta)
                                try:
                                    on_delta(delta)
                                except Exception:
                                    pass
                        except Exception:
                            continue
                    # Build a response-like object for downstream parsing.
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

                    response = _Resp("".join(parts), finish_reason)
                break
            except OpenAIError as exc:
                last_exc = exc
                if rf.get("type") == "json_schema":
                    logger.warning(
                        "OpenAI gateway rejected json_schema; falling back to json_object rid=%s model=%s err=%s",
                        get_request_id(),
                        self.model,
                        exc,
                    )
                    continue
                logger.error("OpenAI chat.completions failed: %s", exc)
                raise RuntimeError("OpenAI request failed") from exc

        if response is None:
            raise RuntimeError("OpenAI request failed") from last_exc

        finish_reason = getattr(response.choices[0], "finish_reason", None)

        content = response.choices[0].message.content or ""
        try:
            data = _parse_json_block(content)
        except ValueError as exc:
            extracted, incomplete = _extract_lenient_top_level_string_fields_with_meta(
                content,
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
