from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Protocol
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
        on_delta: Callable[[str, str, str], None] | None = None,
    ) -> list[ProblemBlock]: ...


class DiagramReconstructorLike(Protocol):
    def run(
        self,
        payload: TaskCreateRequest,
        problems: list[ProblemBlock],
        on_progress: Callable[[int, int, ProblemBlock], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[ProblemBlock]: ...


@dataclass
class PipelineDependencies:
    extractor: HandwrittenExtractor
    solution_writer: SolutionWriter
    tagger: TaggingProfiler
    diagram_reconstructor: DiagramReconstructorLike | None
    archiver: Archiver
    archive_store: ArchiveStore
    ocr_extractor: OcrExtractorLike | None = None


@dataclass
class SegmenterRuntimeAccess:
    """Stable runtime access for the OCR segmenter dependencies."""

    client: Any
    model_resolver: Callable[[str], str | None] | None
    thinking_resolver: Callable[[str], bool | None] | None


class AgentPipeline:
    def __init__(
        self, deps: PipelineDependencies, orchestrator: AgentOrchestrator | None = None
    ) -> None:
        self.deps = deps
        self.orchestrator = orchestrator

    def get_segmenter_runtime_access(self) -> SegmenterRuntimeAccess | None:
        """Return stable accessors for segmenter runtime config, if available."""
        ocr_router = self.deps.ocr_extractor
        if ocr_router is None:
            return None
        llm_extractor = getattr(ocr_router, "llm_extractor", None) or getattr(
            ocr_router, "_llm_extractor", None
        )
        client = getattr(llm_extractor, "client", None)
        if client is None:
            return None

        model_resolver = getattr(ocr_router, "model_resolver", None)
        if not callable(model_resolver):
            model_resolver = None

        thinking_resolver = getattr(ocr_router, "thinking_resolver", None)
        if not callable(thinking_resolver):
            thinking_resolver = None

        return SegmenterRuntimeAccess(
            client=client,
            model_resolver=model_resolver,
            thinking_resolver=thinking_resolver,
        )

    def list_runtime_clients(self) -> list[Any]:
        """Collect active runtime clients exposed by the pipeline."""
        clients: list[Any] = []

        if self.orchestrator is not None:
            for agent in (
                getattr(self.orchestrator, "solver", None),
                getattr(self.orchestrator, "tagger", None),
            ):
                client = getattr(agent, "client", None)
                if client is not None:
                    clients.append(client)

        segmenter_runtime = self.get_segmenter_runtime_access()
        if segmenter_runtime is not None and segmenter_runtime.client is not None:
            clients.append(segmenter_runtime.client)

        # De-duplicate by object identity to avoid repeated reconfigure on shared clients.
        deduped: list[Any] = []
        seen: set[int] = set()
        for client in clients:
            marker = id(client)
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(client)
        return deduped

    def run(
        self,
        task_id: str,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
        on_progress: Callable[[str, str | None], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        existing_problems: list[ProblemBlock] | None = None,
    ) -> PipelineResult:
        def emit(stage: str, message: str | None = None) -> None:
            if on_progress is not None:
                try:
                    on_progress(stage, message)
                except Exception:
                    # 进度上报失败不应影响主流水线。
                    pass

        logger.info(
            "Pipeline start task_id=%s subject=%s has_asset=%s orchestrator=%s enable_ocr=%s has_existing_problems=%s",
            task_id,
            payload.subject,
            bool(asset),
            bool(self.orchestrator),
            self.deps.ocr_extractor is not None,
            bool(existing_problems),
        )
        emit("starting", "开始处理")
        # 从原始试题图（手写或扫描）中提取逻辑题目。
        emit("extracting", "识别题目")
        detection, problems = self._extract(payload, asset, existing_problems)
        if self.deps.diagram_reconstructor is not None and problems:
            total = len(problems)
            emit("diagramming", f"图形重建 0/{total}")
            problems = self.deps.diagram_reconstructor.run(
                payload,
                problems,
                on_progress=lambda i, n, _p: emit("diagramming", f"图形重建 {i}/{n}"),
                is_cancelled=is_cancelled,
            )
            failed_count = sum(
                1 for problem in problems if problem.diagram_render_status == "failed"
            )
            if failed_count > 0:
                emit(
                    "diagramming",
                    f"图形重建完成（{total - failed_count}/{total}），{failed_count}题失败需人工介入",
                )
            else:
                emit("diagramming", f"图形重建完成 {total}/{total}")
        if self.orchestrator:
            # 多 Agent 编排按批次执行。
            solutions, tags = self.orchestrator.solve_and_tag(
                payload,
                problems,
                is_cancelled=is_cancelled,
                on_progress=emit,
            )
        else:
            total = len(problems)
            if total > 0:
                emit("solving", f"解题 0/{total}")
            solutions = self.deps.solution_writer.run(
                payload,
                problems,
                on_progress=lambda i, n, _p: emit("solving", f"解题 {i}/{n}"),
                is_cancelled=is_cancelled,
            )
            if total > 0:
                emit("tagging", f"标注 0/{total}")
            tags = self.deps.tagger.run(
                payload,
                problems,
                solutions,
                on_progress=lambda i, n, _p: emit("tagging", f"标注 {i}/{n}"),
                is_cancelled=is_cancelled,
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
        existing_problems: list[ProblemBlock] | None = None,
    ):
        if asset and self.deps.ocr_extractor:
            # 若基于已有题目重试，复用原 region_id
            if existing_problems:
                region_id = (
                    existing_problems[0].region_id if existing_problems else uuid4().hex
                )
                detection = DetectionOutput(
                    action="single",
                    regions=[
                        CropRegion(
                            id=region_id, bbox=[0.05, 0.05, 0.9, 0.9], label="full"
                        )
                    ],
                )
            else:
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

            # 重试场景下保留原 problem_id 与 region_id
            if existing_problems and problems:
                for idx, problem in enumerate(problems):
                    if idx < len(existing_problems):
                        problem.problem_id = existing_problems[idx].problem_id
                        problem.region_id = existing_problems[idx].region_id

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
        """对单个区域重跑 OCR，并返回新的单题草稿。"""
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
                (lambda delta: on_llm_delta("ocr", "ocr", delta))  # type: ignore[arg-type, misc]
                if on_llm_delta is not None
                else None
            ),
        )
        if not extracted:
            raise RuntimeError("OCR extractor returned empty result")
        return extracted[0]

    def rerender_diagram_for_problem(
        self,
        *,
        payload: TaskCreateRequest,
        problem: ProblemBlock,
    ) -> ProblemBlock:
        """对单个题目重跑图形重建。"""
        if self.deps.diagram_reconstructor is None:
            raise RuntimeError("Diagram reconstructor not configured")
        updated = self.deps.diagram_reconstructor.run(payload, [problem])
        if not updated:
            raise RuntimeError("Diagram reconstructor returned empty result")
        return updated[0]

    def retag_problem(
        self,
        *,
        payload: TaskCreateRequest,
        problem: ProblemBlock,
        solution: SolutionBlock | None,
    ) -> TaggingResult:
        """为单题生成标签，可选传入已有解答。"""
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
        """通过编排器或回退链路，对单题执行解题与打标。"""
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
        """在人工覆盖要求重算标签时，直接对单题执行分类。"""
        return self.retag_problem(payload=payload, problem=problem, solution=None)
