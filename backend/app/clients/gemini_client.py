from __future__ import annotations

import json
import logging
import threading
import os
from pathlib import Path
import time
from typing import Any
from typing import Callable

from pydantic import BaseModel

import google.generativeai as genai

from app.models import ProblemBlock, TaggingResult

from .base import AIClient
from app.request_context import get_request_id
from app.trace import trace_event

logger = logging.getLogger(__name__)
_GENAI_CONFIG_LOCK = threading.Lock()

_PROMPT_DIR = Path(__file__).parent / "prompts"
_PROMPT_CACHE: dict[str, str] = {}


def _load_prompt(filename: str) -> str:
    cached = _PROMPT_CACHE.get(filename)
    if cached is not None:
        return cached
    text = (_PROMPT_DIR / filename).read_text(encoding="utf-8")
    _PROMPT_CACHE[filename] = text
    return text


class GeminiClient(AIClient):
    """Gemini-based AI client using google-generativeai."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.temperature = temperature
        if max_output_tokens is None:
            env_max = os.getenv("GEMINI_MAX_OUTPUT_TOKENS")
            if env_max is not None:
                try:
                    max_output_tokens = int(env_max)
                except ValueError:
                    max_output_tokens = None
        self.max_output_tokens = max_output_tokens if max_output_tokens is not None else 900
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name=model)

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
        data = self._complete_json(system_prompt, user_prompt)
        _maybe_stream_payload(on_delta, data)
        return data

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Best-effort multimodal call.

        If the installed google-generativeai version supports image parts, this will
        send both text and image. Otherwise it falls back to text-only.
        """

        json_only = _load_prompt("json_only_suffix.txt").strip()
        prompt = f"{system_prompt}\n\n{user_prompt}\n{json_only}"
        started = time.perf_counter()
        logger.info(
            "Gemini request rid=%s model=%s has_image=%s approx_chars=%s",
            get_request_id(),
            self.model,
            True,
            len(prompt),
        )
        trace_event(
            "llm_request",
            provider="gemini",
            model=self.model,
            has_image=True,
            approx_chars=len(prompt),
            max_output_tokens=self.max_output_tokens,
        )
        try:
            with _GENAI_CONFIG_LOCK:
                genai.configure(api_key=self._api_key)

            # Newer SDKs support inline data parts.
            part_factory = getattr(getattr(genai, "types", None), "Part", None)
            if part_factory and hasattr(part_factory, "from_data"):
                image_part = part_factory.from_data(data=image_bytes, mime_type=mime_type)
                response = self._model.generate_content(
                    [prompt, image_part],
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": self.max_output_tokens,
                    },
                )
            else:
                response = self._model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": self.max_output_tokens,
                    },
                )
        except Exception as exc:  # pragma: no cover - API errors
            logger.error("Gemini generate_content failed: %s", exc)
            raise RuntimeError("Gemini request failed") from exc

        content = response.text or ""
        try:
            data = _parse_json_block(content)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("Gemini response ok model=%s ms=%.1f", self.model, elapsed_ms)
            trace_event(
                "llm_response",
                provider="gemini",
                model=self.model,
                ok=True,
                keys=sorted(list(data.keys())) if isinstance(data, dict) else [],
                raw_text=content,
                ms=elapsed_ms,
            )
            _maybe_stream_payload(on_delta, data)
            return data
        except ValueError as exc:
            logger.error("Gemini response was not JSON rid=%s: %s", get_request_id(), content)
            trace_event(
                "llm_response",
                provider="gemini",
                model=self.model,
                ok=False,
                raw_text=content,
            )
            raise RuntimeError("Gemini response was not JSON") from exc

    def _complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        json_only = _load_prompt("json_only_suffix.txt").strip()
        prompt = f"{system_prompt}\n\n{user_prompt}\n{json_only}"
        started = time.perf_counter()
        logger.info(
            "Gemini request rid=%s model=%s has_image=%s approx_chars=%s",
            get_request_id(),
            self.model,
            False,
            len(prompt),
        )
        trace_event(
            "llm_request",
            provider="gemini",
            model=self.model,
            has_image=False,
            approx_chars=len(prompt),
            max_output_tokens=self.max_output_tokens,
        )
        try:
            with _GENAI_CONFIG_LOCK:
                # google-generativeai uses a global config; guard it for per-agent keys.
                genai.configure(api_key=self._api_key)
            response = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_output_tokens,
                },
            )
        except Exception as exc:  # pragma: no cover - API errors
            logger.error("Gemini generate_content failed: %s", exc)
            raise RuntimeError("Gemini request failed") from exc

        content = response.text or ""
        try:
            data = _parse_json_block(content)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("Gemini response ok model=%s ms=%.1f", self.model, elapsed_ms)
            trace_event(
                "llm_response",
                provider="gemini",
                model=self.model,
                ok=True,
                keys=sorted(list(data.keys())) if isinstance(data, dict) else [],
                raw_text=content,
                ms=elapsed_ms,
            )
            return data
        except ValueError as exc:
            logger.error("Gemini response was not JSON rid=%s: %s", get_request_id(), content)
            trace_event(
                "llm_response",
                provider="gemini",
                model=self.model,
                ok=False,
                raw_text=content,
            )
            raise RuntimeError("Gemini response was not JSON") from exc

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

    decoder = json.JSONDecoder()
    candidate = text[start:]
    try:
        obj, _end = decoder.raw_decode(candidate)
        if not isinstance(obj, dict):
            raise ValueError("JSON root was not an object")
        return obj
    except json.JSONDecodeError as exc:
        logger.info("Gemini JSON repair triggered")
        repaired = _repair_invalid_string_escapes(candidate)
        repaired = _strip_disallowed_control_chars_outside_strings(repaired)
        repaired = _remove_trailing_commas(repaired)
        try:
            obj, _end = decoder.raw_decode(repaired)
        except json.JSONDecodeError as exc2:
            _log_json_decode_error("Gemini", candidate, exc, repaired, exc2)
            raise
        if not isinstance(obj, dict):
            raise ValueError("JSON root was not an object")
        return obj


def _maybe_stream_payload(on_delta: Callable[[str], None] | None, payload: dict[str, Any]) -> None:
    if on_delta is None:
        return
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    for i in range(0, len(text), 24):
        try:
            on_delta(text[i : i + 24])
        except Exception:
            break


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
        "%s JSON parse failed even after repair. original=(line=%s col=%s pos=%s msg=%s) repaired=(line=%s col=%s pos=%s msg=%s) original_around=%r repaired_around=%r",
        label,
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
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(snippet):
        ch = snippet[i]

        if in_string and ch in ("\n", "\r", "\t"):
            if ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            else:
                out.append("\\t")
            i += 1
            continue

        if in_string and isinstance(ch, str) and ch and ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
            i += 1
            continue

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

        if in_string and ch == "\\":
            if i + 1 >= len(snippet):
                out.append("\\\\")
                i += 1
                continue

            nxt = snippet[i + 1]
            if nxt in ("b", "f", "n", "r", "t") and i + 2 < len(snippet) and snippet[i + 2].isalpha():
                out.append("\\\\")
                i += 1
                continue

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
            if ch.isspace() and ch not in ("\t", "\n", "\r", " "):
                out.append(" ")
                i += 1
                continue

            if ord(ch) < 0x20 and ch not in ("\t", "\n", "\r", " "):
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _remove_trailing_commas(snippet: str) -> str:
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


def _ensure_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return fallback
