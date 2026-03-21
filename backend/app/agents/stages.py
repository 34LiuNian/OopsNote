from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Callable, Iterable, List, Tuple
from uuid import uuid4

from ..clients import AIClient
from ..models import (
    ArchiveRecord,
    CropRegion,
    DetectionOutput,
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    TaskCreateRequest,
)
from . import utils

# Re-export PromptTemplate for backward compatibility
from .agent_flow import PromptTemplate


def _load_prompt(name: str) -> "PromptTemplate":
    """Load a prompt template (legacy wrapper, use utils._load_prompt instead)."""
    return utils._load_prompt(name)


# Note: Type coercion helpers moved to utils.py
# - _coerce_list
# - _coerce_str


class HandwrittenExtractor:
    def __init__(self, rebuilder: "ProblemRebuilder") -> None:
        self.rebuilder = rebuilder

    def run(
        self, payload: TaskCreateRequest
    ) -> Tuple[DetectionOutput, List[ProblemBlock]]:
        detection = DetectionOutput(
            action="single",
            regions=[
                CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
            ],
        )
        problems = self.rebuilder.run(payload, detection)
        return detection, problems


class ProblemRebuilder:
    def run(
        self, payload: TaskCreateRequest, detection: DetectionOutput
    ) -> List[ProblemBlock]:
        raise RuntimeError(
            "ProblemRebuilder (placeholders) is disabled. Please provide an image for OCR."
        )


class DiagramReconstructor:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client
        self._template = _load_prompt("diagram")

    @staticmethod
    def _extract_tikz_source(problem_text: str) -> str | None:
        text = (problem_text or "").strip()
        if not text:
            return None

        fence_match = re.search(r"```tikz\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            source = (fence_match.group(1) or "").strip()
            if source:
                return source

        env_match = re.search(
            r"(\\begin\{tikzpicture\}.*?\\end\{tikzpicture\})",
            text,
            flags=re.DOTALL,
        )
        if env_match:
            source = (env_match.group(1) or "").strip()
            if source:
                return source

        return None

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        on_progress: Callable[[int, int, ProblemBlock], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> List[ProblemBlock]:
        problems_list = list(problems)
        updated: list[ProblemBlock] = []
        total = len(problems_list)

        for idx, problem in enumerate(problems_list, start=1):
            if is_cancelled and is_cancelled():
                from ..services.tasks_service import _TaskCancelled

                raise _TaskCancelled("Task was cancelled by user")
            if on_progress:
                on_progress(idx, total, problem)

            if not bool(getattr(problem, "ocr_has_diagram", False)):
                updated.append(
                    problem.model_copy(
                        update={
                            "diagram_detected": False,
                            "diagram_kind": None,
                            "diagram_tikz_source": None,
                            "diagram_svg": None,
                            "diagram_render_status": "skipped",
                            "diagram_error": None,
                            "diagram_needs_review": False,
                            "diagram_confidence": None,
                        }
                    )
                )
                continue

            tikz_source = self._extract_tikz_source(problem.problem_text)
            try:
                confidence = 1.0
                if not tikz_source:
                    if self.ai_client is None:
                        raise RuntimeError("Diagram agent client is not configured")
                    ctx = {
                        "subject": problem.subject or payload.subject,
                        "question_type": problem.question_type or "",
                        "problem_text": problem.problem_text,
                    }
                    system_prompt, user_prompt = self._template.render(ctx)
                    output = self.ai_client.structured_chat(system_prompt, user_prompt)
                    has_diagram = bool(output.get("has_diagram"))
                    if not has_diagram:
                        updated.append(
                            problem.model_copy(
                                update={
                                    "diagram_detected": False,
                                    "diagram_kind": None,
                                    "diagram_tikz_source": None,
                                    "diagram_svg": None,
                                    "diagram_render_status": "skipped",
                                    "diagram_error": utils._coerce_str(
                                        output.get("reason"), None
                                    ),
                                    "diagram_needs_review": False,
                                    "diagram_confidence": None,
                                }
                            )
                        )
                        continue

                    tikz_source = utils._coerce_str(output.get("tikz_source"), None)
                    if not tikz_source:
                        updated.append(
                            problem.model_copy(
                                update={
                                    "diagram_detected": False,
                                    "diagram_kind": None,
                                    "diagram_tikz_source": None,
                                    "diagram_svg": None,
                                    "diagram_render_status": "failed",
                                    "diagram_error": "diagram agent returned empty tikz_source",
                                    "diagram_needs_review": True,
                                    "diagram_confidence": None,
                                }
                            )
                        )
                        continue

                    confidence_raw = output.get("confidence")
                    if confidence_raw is not None:
                        try:
                            confidence = float(confidence_raw)
                        except (TypeError, ValueError):
                            confidence = 1.0

                svg_text = None
                render_status = "ready"
                render_error = None
                needs_review = False
                try:
                    from ..api.latex import render_tikz_svg_bytes

                    svg_bytes = render_tikz_svg_bytes(tikz_source, inline=False)
                    svg_text = svg_bytes.decode("utf-8", errors="replace")
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    render_status = "failed"
                    render_error = str(exc)
                    needs_review = True

                updated.append(
                    problem.model_copy(
                        update={
                            "diagram_detected": True,
                            "diagram_kind": "tikz",
                            "diagram_tikz_source": tikz_source,
                            "diagram_svg": svg_text,
                            "diagram_render_status": render_status,
                            "diagram_error": render_error,
                            "diagram_needs_review": needs_review,
                            "diagram_confidence": confidence,
                        }
                    )
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                updated.append(
                    problem.model_copy(
                        update={
                            "diagram_detected": False,
                            "diagram_kind": None,
                            "diagram_tikz_source": None,
                            "diagram_svg": None,
                            "diagram_render_status": "failed",
                            "diagram_error": str(exc),
                            "diagram_needs_review": True,
                            "diagram_confidence": None,
                        }
                    )
                )

        return updated


class SolutionWriter:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client
        self._template = _load_prompt("solver")

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        on_progress: Callable[[int, int, ProblemBlock], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> List[SolutionBlock]:
        problems_list = list(problems)
        solved: List[SolutionBlock] = []
        total = len(problems_list)

        for idx, problem in enumerate(problems_list, start=1):
            if is_cancelled and is_cancelled():
                from ..services.tasks_service import _TaskCancelled

                raise _TaskCancelled("Task was cancelled by user")
            if on_progress:
                on_progress(idx, total, problem)

            ctx = {
                "subject": payload.subject,
                "grade": payload.grade or "",
                "problem_text": problem.problem_text,
            }
            system_prompt, user_prompt = self._template.render(ctx)

            output = self.ai_client.structured_chat(system_prompt, user_prompt)
            answer = output.get("answer")
            explanation = output.get("explanation")
            if not answer or not explanation:
                raise RuntimeError(
                    f"Solver failed: missing answer or explanation for problem {problem.problem_id}"
                )

            solved.append(
                SolutionBlock(
                    problem_id=problem.problem_id,
                    answer=str(answer),
                    explanation=str(explanation),
                    short_answer=utils._coerce_str(output.get("short_answer"), None),
                )
            )
        return solved


class TaggingProfiler:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client
        self._template = _load_prompt("tagger")

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        solutions: Iterable[SolutionBlock],
        on_progress: Callable[[int, int, ProblemBlock], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> List[TaggingResult]:
        problems_list = list(problems)
        solutions_map = {s.problem_id: s for s in solutions}
        tags: List[TaggingResult] = []
        total = len(problems_list)

        for idx, problem in enumerate(problems_list, start=1):
            if is_cancelled and is_cancelled():
                from ..services.tasks_service import _TaskCancelled

                raise _TaskCancelled("Task was cancelled by user")
            if on_progress:
                on_progress(idx, total, problem)

            solution = solutions_map.get(problem.problem_id)
            ctx = {
                "subject": payload.subject,
                "grade": payload.grade or "",
                "problem_text": problem.problem_text,
                "explanation": solution.explanation if solution else "",
                "answer": solution.answer if solution else "",
                "manual_knowledge_tags": "",  # Current pipeline doesn't have a clean way to inject these here yet
                "manual_error_tags": "",
                "manual_source": "",
                "meta_candidates": "",
                "knowledge_candidates": "",
                "error_candidates": "",
            }
            system_prompt, user_prompt = self._template.render(ctx)

            output = self.ai_client.structured_chat(system_prompt, user_prompt)

            # Ensure key fields exist
            if not output.get("knowledge_points") or not output.get("question_type"):
                raise RuntimeError(
                    f"Tagger failed: missing essential fields for problem {problem.problem_id}"
                )

            tags.append(
                TaggingResult(
                    problem_id=problem.problem_id,
                    knowledge_points=utils._coerce_list(
                        output.get("knowledge_points"), []
                    ),
                    question_type=str(output.get("question_type")),
                    skills=utils._coerce_list(output.get("skills"), []),
                    error_hypothesis=utils._coerce_list(
                        output.get("error_hypothesis"), []
                    ),
                    recommended_actions=utils._coerce_list(
                        output.get("recommended_actions"), []
                    ),
                )
            )
        return tags


class Archiver:
    def run(self, task_id: str, problems: Iterable[ProblemBlock]) -> ArchiveRecord:
        return ArchiveRecord(
            task_id=task_id,
            stored_problem_ids=[p.problem_id for p in problems],
            timestamp=datetime.now(timezone.utc),
        )
