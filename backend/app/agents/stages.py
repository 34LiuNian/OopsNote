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


def _derive_problem_count(payload: TaskCreateRequest) -> int:
    if payload.mock_problem_count:  # explicit override for demos/tests
        return payload.mock_problem_count

    if payload.notes:
        lowered = payload.notes.lower()
        if "multi" in lowered or "两" in lowered:
            return 2
        if "三" in lowered or "triple" in lowered:
            return 3
    return 1


class MultiProblemDetector:
    def run(self, payload: TaskCreateRequest) -> DetectionOutput:
        count = _derive_problem_count(payload)
        action: DetectionOutput = DetectionOutput(action="single", regions=[])
        if count == 1:
            if payload.notes and "fragment" in payload.notes.lower():
                action.action = "single-noise"
                action.regions = [
                    CropRegion(
                        id=uuid4().hex,
                        bbox=[0.05, 0.05, 0.9, 0.9],
                        label="full",
                    )
                ]
            return action

        regions = []
        for idx in range(count):
            regions.append(
                CropRegion(
                    id=uuid4().hex,
                    bbox=[0.05, 0.05 + idx * 0.3, 0.9, 0.25],
                    label="full" if idx == 0 else "partial",
                )
            )
        action.action = "multi"
        action.regions = regions
        return action


class HandwrittenExtractor:
    """Composite stage: detect multi-problem layout, then rebuild logical problems.

    Today this is rule-based; later it can be swapped for real OCR / multimodal models
    without touching the rest of the pipeline.
    """

    def __init__(self, detector: "MultiProblemDetector", rebuilder: "ProblemRebuilder") -> None:
        self.detector = detector
        self.rebuilder = rebuilder

    def run(self, payload: TaskCreateRequest) -> Tuple[DetectionOutput, List[ProblemBlock]]:
        detection = self.detector.run(payload)
        problems = self.rebuilder.run(payload, detection)
        return detection, problems


class ProblemRebuilder:
    def run(self, payload: TaskCreateRequest, detection: DetectionOutput) -> List[ProblemBlock]:
        regions = detection.regions or [
            CropRegion(
                id=uuid4().hex,
                bbox=[0.05, 0.05, 0.9, 0.9],
                label="full",
            )
        ]
        problems: List[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            latex = (
                r"$$ F = ma $$" if payload.subject.lower().startswith("phy") else r"$$ a^2 + b^2 = c^2 $$"
            )
            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    question_no=payload.question_no,
                    problem_text=(
                        "根据图示求解未知量" if payload.subject.lower().startswith("phy") else "求解直角三角形未知边"
                    ),
                    latex_blocks=[latex],
                    media_notes="Auto rebuilt from detector results",
                    source=payload.notes or None,
                    crop_bbox=region.bbox,
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
        for idx, problem in enumerate(problems_list, start=1):
            if on_progress is not None:
                try:
                    on_progress(idx, total, problem)
                except Exception:
                    pass
            answer, explanation = self.ai_client.generate_solution(
                payload.subject,
                problem,
                on_delta=(lambda delta, p=problem: on_token(p, delta)) if on_token is not None else None,
            )
            solved.append(
                SolutionBlock(
                    problem_id=problem.problem_id,
                    answer=answer,
                    explanation=explanation,
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
        for idx, problem in enumerate(problems_list, start=1):
            if on_progress is not None:
                try:
                    on_progress(idx, total, problem)
                except Exception:
                    pass
            tags.append(self.ai_client.classify_problem(payload.subject, problem))
        return tags


class Archiver:
    def run(self, task_id: str, problems: Iterable[ProblemBlock]) -> ArchiveRecord:
        return ArchiveRecord(
            task_id=task_id,
            stored_problem_ids=[problem.problem_id for problem in problems],
            timestamp=datetime.now(timezone.utc),
        )