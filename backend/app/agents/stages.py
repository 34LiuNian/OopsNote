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

def _format_problem_prompt(subject: str, problem: ProblemBlock) -> str:
    latex = "\n".join(problem.latex_blocks)
    return (
        f"学科: {subject}\n"
        f"题干: {problem.problem_text}\n"
        f"Latex: {latex if latex else 'N/A'}"
    )

def _coerce_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return fallback

class HandwrittenExtractor:
    def __init__(self, rebuilder: "ProblemRebuilder") -> None:
        self.rebuilder = rebuilder

    def run(self, payload: TaskCreateRequest) -> Tuple[DetectionOutput, List[ProblemBlock]]:
        detection = DetectionOutput(
            action="single",
            regions=[CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")]
        )
        problems = self.rebuilder.run(payload, detection)
        return detection, problems

class ProblemRebuilder:
    def run(self, payload: TaskCreateRequest, detection: DetectionOutput) -> List[ProblemBlock]:
        regions = detection.regions or [
            CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
        ]
        problems: List[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    question_no=payload.question_no,
                    problem_text="求解中...",
                    latex_blocks=[],
                    media_notes="Auto rebuilt",
                    source=payload.notes or None,
                )
            )
        return problems

class SolutionWriter:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        on_progress: Callable[[int, int, ProblemBlock], None] | None = None,
        on_token: Callable[[ProblemBlock, str], None] | None = None,
    ) -> List[SolutionBlock]:
        problems_list = list(problems)
        solved: List[SolutionBlock] = []
        total = len(problems_list)
        system_prompt = "你是一个解题助手。根据提供的题目内容，给出清晰的答案和解析。输出严格 JSON，包含字段: answer, explanation, short_answer。"

        for idx, problem in enumerate(problems_list, start=1):
            if on_progress: on_progress(idx, total, problem)
            user_prompt = _format_problem_prompt(payload.subject, problem)
            output = self.ai_client.structured_chat(
                system_prompt,
                user_prompt,
                on_delta=(lambda d, p=problem: on_token(p, d)) if on_token else None,
            )
            solved.append(
                SolutionBlock(
                    problem_id=problem.problem_id,
                    answer=str(output.get("answer", "无答案")),
                    explanation=str(output.get("explanation", "无解析")),
                    short_answer=str(output.get("short_answer", "")),
                )
            )
        return solved

class TaggingProfiler:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        solutions: Iterable[SolutionBlock],
        on_progress: Callable[[int, int, ProblemBlock], None] | None = None,
    ) -> List[TaggingResult]:
        problems_list = list(problems)
        tags: List[TaggingResult] = []
        total = len(problems_list)
        system_prompt = "你是一个教育专家。请分析题目并返回 JSON，包含字段: knowledge_points (list), question_type (str), skills (list), error_hypothesis (list), recommended_actions (list)。"

        for idx, problem in enumerate(problems_list, start=1):
            if on_progress: on_progress(idx, total, problem)
            user_prompt = _format_problem_prompt(payload.subject, problem)
            output = self.ai_client.structured_chat(system_prompt, user_prompt)
            tags.append(
                TaggingResult(
                    problem_id=problem.problem_id,
                    knowledge_points=_coerce_list(output.get("knowledge_points"), ["未标注"]),
                    question_type=str(output.get("question_type", "解答题")),
                    skills=_coerce_list(output.get("skills"), ["默认能力"]),
                    error_hypothesis=_coerce_list(output.get("error_hypothesis"), ["待查"]),
                    recommended_actions=_coerce_list(output.get("recommended_actions"), ["复习相关知识点"]),
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
