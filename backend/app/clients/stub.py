from __future__ import annotations

import random
import json
from typing import Any, Callable

from pydantic import BaseModel

from app.models import ProblemBlock, TaggingResult

from .base import AIClient


class StubAIClient:
    """Deterministic AI client used for local development without API keys."""

    model = "stub-local-v1"

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def generate_solution(
        self,
        subject: str,
        problem: ProblemBlock,
        on_delta: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        if subject.lower().startswith("phy"):
            answer = "a = F / m"
            explanation = (
                "1. 根据题意列出牛顿第二定律; "
                "2. 将力和质量代入 F = ma; "
                "3. 化简得到 a = F / m。"
            )
        else:
            answer = "c = sqrt(a^2 + b^2)"
            explanation = (
                "1. 识别直角三角形; "
                "2. 应用勾股定理 a^2 + b^2 = c^2; "
                "3. 求出所需未知量。"
            )

        if on_delta is not None:
            # Simulate token streaming by chunking the JSON-ish content.
            text = json.dumps({"answer": answer, "explanation": explanation}, ensure_ascii=False)
            for i in range(0, len(text), 12):
                try:
                    on_delta(text[i : i + 12])
                except Exception:
                    break
        return answer, explanation

    def classify_problem(self, subject: str, problem: ProblemBlock) -> TaggingResult:
        knowledge = ["勾股定理"] if subject.lower().startswith("math") else ["牛顿第二定律"]
        skills = ["几何推理"] if subject.lower().startswith("math") else ["物理建模", "代数推导"]
        return TaggingResult(
            problem_id=problem.problem_id,
            knowledge_points=knowledge,
            question_type="解答题",
            skills=skills,
            error_hypothesis=["审题不清", "计算缺陷"],
            recommended_actions=["回顾公式", "针对性练习 3 道题"],
        )

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        lower = (system_prompt + "\n" + user_prompt).lower()

        # Tagger
        if "knowledge_points" in lower or "question_type" in lower:
            payload = {
                "knowledge_points": ["勾股定理"],
                "question_type": "解答题",
                "skills": ["分析推理"],
                "error_hypothesis": ["审题不清"],
                "recommended_actions": ["回顾公式"],
            }
            _maybe_stream_payload(on_delta, payload)
            return payload

        # Default solver-like
        payload = {
            "answer": "(stub) answer",
            "explanation": "(stub) explanation",
            "short_answer": "(stub)",
        }
        _maybe_stream_payload(on_delta, payload)
        return payload

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        lower = (system_prompt + "\n" + user_prompt).lower()

        # OCR branch (expects problem_text/latex_blocks/etc).
        if "ocr" in lower or "problem_text" in lower:
            payload = {
                "problem_text": "【LLM-OCR 占位】请根据图中内容作答",
                "latex_blocks": [r"$$ a^2 + b^2 = c^2 $$"],
                "options": [],
                "ocr_text": "stub ocr text",
            }
            _maybe_stream_payload(on_delta, payload)
            return payload

        # Default: fall back to OCR-like output.
        payload = {
            "problem_text": "【LLM-OCR 占位】请根据图中内容作答",
            "latex_blocks": [],
            "options": [],
            "ocr_text": "stub ocr text",
        }
        _maybe_stream_payload(on_delta, payload)
        return payload


def _maybe_stream_payload(on_delta: Callable[[str], None] | None, payload: dict[str, Any]) -> None:
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
