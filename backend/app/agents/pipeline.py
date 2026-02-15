from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable, Protocol
from uuid import uuid4

from ..models import (
    AssetMetadata,
    CropRegion,
    DetectionOutput,
    PipelineResult,
    ProblemBlock,
    SolutionBlock,
    TaskCreateRequest,
    TaggingResult,
)
from ..repository import ArchiveStore
from .agent_flow import AgentOrchestrator
from .stages import Archiver, HandwrittenExtractor, SolutionWriter, TaggingProfiler

logger = logging.getLogger(__name__)


class OcrExtractorLike(Protocol):
    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
    ) -> list[ProblemBlock]: ...


@dataclass
class PipelineDependencies:
    extractor: HandwrittenExtractor
    solution_writer: SolutionWriter
    tagger: TaggingProfiler
    archiver: Archiver
    archive_store: ArchiveStore
    ocr_extractor: OcrExtractorLike | None = None


class AgentPipeline:
    def __init__(
        self, deps: PipelineDependencies, orchestrator: AgentOrchestrator | None = None
    ) -> None:
        self.deps = deps
        self.orchestrator = orchestrator

    def run(
        self,
        task_id: str,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
        on_progress: Callable[[str, str | None], None] | None = None,
    ) -> PipelineResult:
        def emit(stage: str, message: str | None = None) -> None:
            if on_progress is not None:
                try:
                    on_progress(stage, message)
                except Exception:
                    # Progress reporting must not break the pipeline.
                    pass

        logger.info(
            "Pipeline start task_id=%s subject=%s has_asset=%s orchestrator=%s enable_ocr=%s",
            task_id,
            payload.subject,
            bool(asset),
            bool(self.orchestrator),
            self.deps.ocr_extractor is not None,
        )
        emit("starting", "开始处理")
        # Extract logical problems from the original sheet (handwritten or scanned).
        emit("extracting", "识别题目")
        detection, problems = self._extract(payload, asset)
        if self.orchestrator:
            # Multi-agent orchestration runs as a batch; keep coarse updates.
            solutions, tags = self.orchestrator.solve_and_tag(
                payload, problems
            )
        else:
            total = len(problems)
            if total > 0:
                emit("solving", f"解题 0/{total}")
            solutions = self.deps.solution_writer.run(
                payload,
                problems,
                on_progress=lambda i, n, _p: emit("solving", f"解题 {i}/{n}"),
            )
            if total > 0:
                emit("tagging", f"标注 0/{total}")
            tags = self.deps.tagger.run(
                payload,
                problems,
                solutions,
                on_progress=lambda i, n, _p: emit("tagging", f"标注 {i}/{n}"),
            )

        emit("archiving", "归档")
        archive = self.deps.archiver.run(task_id, problems)
        self.deps.archive_store.save(archive)
        logger.info(
            "Pipeline done task_id=%s solutions=%s tags=%s",
            task_id,
            len(solutions),
            len(tags),
        )

        emit("done", "完成")
        return PipelineResult(
            detection=detection,
            problems=problems,
            solutions=solutions,
            tags=tags,
            archive=archive,
        )

    def _extract(
        self,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None,
    ):
        if asset and self.deps.ocr_extractor:
            detection = DetectionOutput(
                action="single",
                regions=[
                    CropRegion(
                        id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full"
                    )
                ],
            )

            logger.info(
                "Recognize OCR start regions=%s",
                len(detection.regions or []),
            )
            problems = self.deps.ocr_extractor.run(
                payload,
                detection,
                asset,
            )
            logger.info("Recognize OCR done problems=%s", len(problems))
            return detection, problems
        detection, problems = self.deps.extractor.run(payload)
        return detection, problems

    def rerun_ocr_for_problem(
        self,
        *,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None,
        region_id: str,
        crop_bbox: list[float] | None,
        on_llm_delta: Callable[[str, str, str], None] | None = None,
    ) -> ProblemBlock:
        """Re-run OCR for one region and return a fresh single problem draft."""
        extractor = self.deps.ocr_extractor
        if extractor is None:
            raise RuntimeError("OCR extractor not configured")
        bbox = crop_bbox or [0.05, 0.05, 0.9, 0.25]
        detection = DetectionOutput(
            action="single",
            regions=[CropRegion(id=region_id, bbox=bbox, label="full")],
        )
        extracted = extractor.run(
            payload,
            detection,
            asset,
            on_delta=(
                (lambda delta: on_llm_delta("ocr", "ocr", delta))
                if on_llm_delta is not None
                else None
            ),
        )
        if not extracted:
            raise RuntimeError("OCR extractor returned empty result")
        return extracted[0]

    def retag_problem(
        self,
        *,
        payload: TaskCreateRequest,
        problem: ProblemBlock,
        solution: SolutionBlock | None,
    ) -> TaggingResult:
        """Generate tags for a single problem with an optional existing solution."""
        tags = self.deps.tagger.run(payload, [problem], [solution] if solution else [])
        if not tags:
            raise RuntimeError("Tagger returned empty result")
        return tags[0]

    def solve_and_tag_single(
        self,
        *,
        payload: TaskCreateRequest,
        problem: ProblemBlock,
    ) -> tuple[SolutionBlock, TaggingResult]:
        """Solve and tag one problem through orchestrator or fallback stage chain."""
        if self.orchestrator:
            solutions, tags = self.orchestrator.solve_and_tag(payload, [problem])
        else:
            solutions = self.deps.solution_writer.run(payload, [problem])
            tags = self.deps.tagger.run(payload, [problem], solutions)
        if not solutions or not tags:
            raise RuntimeError("Solve/tag pipeline returned empty result")
        return solutions[0], tags[0]

    def classify_problem(
        self,
        *,
        payload: TaskCreateRequest,
        problem: ProblemBlock,
    ) -> TaggingResult:
        """Classify one problem directly when manual override requests explicit tag recompute."""
        return self.retag_problem(payload=payload, problem=problem, solution=None)
