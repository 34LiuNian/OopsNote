from __future__ import annotations

from typing import Any, Callable, Protocol

from pydantic import BaseModel

from app.models import ProblemBlock, TaggingResult


class AIClient(Protocol):
    """Contract for LLM-powered helpers used by the agent pipeline."""

    model: str

    def generate_solution(
        self,
        subject: str,
        problem: ProblemBlock,
        on_delta: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        """Return (answer, explanation) strings for the given problem."""

    def classify_problem(self, subject: str, problem: ProblemBlock) -> TaggingResult:
        """Return tagging metadata (knowledge points, etc)."""

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """Generic structured generation that returns a JSON-like dict."""

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
        """Structured generation that can also consume a single image."""
