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
    TaskCreateRequest,
)
from ..repository import ArchiveStore
from .agent_flow import AgentOrchestrator
from .stages import Archiver, HandwrittenExtractor, SolutionWriter, TaggingProfiler
from ..trace import trace_event

logger = logging.getLogger(__name__)


class OcrExtractorLike(Protocol):
    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
        on_delta: Callable[[str], None] | None = None,
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
        on_llm_delta: Callable[[str, str, str], None] | None = None,
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
        trace_event(
            "pipeline_start",
            task_id=task_id,
            subject=payload.subject,
            has_asset=bool(asset),
            orchestrator=bool(self.orchestrator),
            enable_ocr=self.deps.ocr_extractor is not None,
        )
        # Extract logical problems from the original sheet (handwritten or scanned).
        emit("extracting", "识别题目")
        detection, problems = self._extract(payload, asset, on_llm_delta=on_llm_delta)
        if problems and (payload.question_type or payload.options):
            if len(problems) == 1:
                updated = problems[0].model_copy(
                    update={
                        "question_type": payload.question_type
                        or problems[0].question_type,
                        "options": payload.options or problems[0].options,
                    }
                )
                problems = [updated]
        logger.info(
            "Pipeline extracted task_id=%s problems=%s regions=%s",
            task_id,
            len(problems),
            len(detection.regions or []),
        )
        trace_event(
            "pipeline_extracted",
            task_id=task_id,
            problems=len(problems),
            regions=len(detection.regions or []),
            action=detection.action,
        )
        emit("solving", "解题与标注")
        if self.orchestrator:
            # Multi-agent orchestration runs as a batch; keep coarse updates.
            solutions, tags = self.orchestrator.solve_and_tag(
                payload, problems, on_llm_delta=on_llm_delta
            )
        else:
            total = len(problems)
            if total > 0:
                emit("solving", f"解题 0/{total}")
            solutions = self.deps.solution_writer.run(
                payload,
                problems,
                on_progress=lambda i, n, _p: emit("solving", f"解题 {i}/{n}"),
                on_token=(
                    (lambda p, delta: on_llm_delta(p.problem_id, "solution", delta))
                    if on_llm_delta is not None
                    else None
                ),
            )
            if total > 0:
                emit("tagging", f"标注 0/{total}")
            tags = self.deps.tagger.run(
                payload,
                problems,
                solutions,
                on_progress=lambda i, n, _p: emit("tagging", f"标注 {i}/{n}"),
            )
        trace_event(
            "pipeline_solved",
            task_id=task_id,
            solutions=len(solutions),
            tags=len(tags),
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
        trace_event(
            "pipeline_done",
            task_id=task_id,
            solutions=len(solutions),
            tags=len(tags),
            archive_items=len(archive.items)
            if hasattr(archive, "items") and archive.items is not None
            else None,
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
        on_llm_delta: Callable[[str, str, str], None] | None = None,
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
                on_delta=(
                    (lambda delta: on_llm_delta("ocr", "ocr", delta))
                    if on_llm_delta is not None
                    else None
                ),
            )
            logger.info("Recognize OCR done problems=%s", len(problems))
            return detection, problems
        detection, problems = self.deps.extractor.run(payload)
        return detection, problems
