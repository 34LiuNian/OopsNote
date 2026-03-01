from __future__ import annotations

from datetime import datetime, timezone
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
