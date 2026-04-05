"""OopsNote 后端领域服务。

本模块按领域职责组织核心业务逻辑，遵循高内聚原则：
每个服务聚焦单一职责。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from .models import (
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    AssetMetadata,
    DetectionOutput,
)
from .protocols import (
    Extractor,
    Solver,
    Tagger,
    Archiver,
    Repository,
    EventBus,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """任务处理流水线的上下文对象。

    封装处理过程中的全部数据，便于：
    - 在各阶段之间传递数据
    - 新增上下文字段时不修改函数签名
    - 对单个阶段做隔离测试
    """

    task_id: str
    payload: TaskCreateRequest
    asset: AssetMetadata | None = None
    detection: DetectionOutput | None = None
    problems: list[ProblemBlock] = None  # type: ignore[assignment]
    solutions: list[SolutionBlock] = None  # type: ignore[assignment]
    tags: list[TaggingResult] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.problems is None:
            self.problems = []
        if self.solutions is None:
            self.solutions = []
        if self.tags is None:
            self.tags = []


class ExtractionService:
    """题目提取服务。

    单一职责：处理题目提取相关逻辑，包括 OCR 与手动重建。
    """

    def __init__(self, extractor: Extractor) -> None:
        self.extractor = extractor

    def extract_problems(
        self,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
    ) -> tuple[DetectionOutput, list[ProblemBlock]]:
        """从上传图片中提取题目。

        Args:
            payload: 含元数据的任务创建请求
            asset: 可选资源元数据

        Returns:
            （检测结果，提取出的题目列表）
        """
        # 单题图片默认检测框
        from .models import CropRegion
        from uuid import uuid4

        detection = DetectionOutput(
            action="single",
            regions=[
                CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
            ],
        )

        problems = self.extractor.run(payload, detection, asset)
        return detection, problems


class SolvingService:
    """题目求解服务。

    单一职责：处理解答生成相关逻辑。
    """

    def __init__(self, solver: Solver) -> None:
        self.solver = solver

    def generate_solutions(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[SolutionBlock]:
        """为题目生成解答。

        Args:
            payload: 任务创建请求
            problems: 待求解题目
            on_progress: 可选进度回调

        Returns:
            生成的解答列表
        """
        problems_list = list(problems)
        total = len(problems_list)

        solutions = []
        for idx, problem in enumerate(problems_list, start=1):
            if on_progress:
                on_progress(idx, total)

            # 单题求解
            problem_solutions = self.solver.run(payload, [problem])
            solutions.extend(problem_solutions)

        return solutions


class TaggingService:
    """题目打标服务。

    单一职责：处理标签与分类逻辑。
    """

    def __init__(self, tagger: Tagger) -> None:
        self.tagger = tagger

    def generate_tags(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        solutions: Iterable[SolutionBlock],
    ) -> list[TaggingResult]:
        """为已解答题目生成标签。

        Args:
            payload: 任务创建请求
            problems: 待打标签题目
            solutions: 对应解答

        Returns:
            标签结果列表
        """
        return self.tagger.run(payload, problems, solutions)


class ArchivingService:
    """任务归档服务。

    单一职责：处理归档相关逻辑。
    """

    def __init__(self, archiver: Archiver) -> None:
        self.archiver = archiver

    def archive_task(
        self,
        task_id: str,
        problems: Iterable[ProblemBlock],
    ):
        """归档已处理任务。

        Args:
            task_id: 任务 ID
            problems: 待归档题目

        Returns:
            归档记录
        """
        return self.archiver.run(task_id, problems)


class TaskProcessingService:
    """完整任务处理流水线编排器。

    单一职责：协调“提取 -> 求解 -> 打标 -> 归档”流程，
    自身不实现各阶段的具体处理逻辑。

    遵循接口原则：
    - 依赖抽象（protocol），而非具体实现
    - 便于测试替换与多配置切换
    """

    def __init__(
        self,
        extraction: ExtractionService,
        solving: SolvingService,
        tagging: TaggingService,
        archiving: ArchivingService,
        repository: Repository,
        event_bus: EventBus,
    ) -> None:
        self.extraction = extraction
        self.solving = solving
        self.tagging = tagging
        self.archiving = archiving
        self.repository = repository
        self.event_bus = event_bus

    def process_task(
        self,
        task_id: str,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
    ) -> ProcessingContext:
        """通过完整流水线处理任务。

        Args:
            task_id: 任务 ID
            payload: 任务创建请求
            asset: 可选资源元数据

        Returns:
            包含全部结果的处理上下文
        """
        context = ProcessingContext(task_id=task_id, payload=payload, asset=asset)

        try:
            # 更新状态
            from .models import TaskStatus
            
            now = datetime.now(timezone.utc)
            self.repository.update_task(
                TaskRecord(
                    id=task_id,
                    payload=payload,
                    status=TaskStatus.PROCESSING,
                    created_at=now,
                    updated_at=now,
                )
            )

            # 阶段 1：提取
            self.event_bus.publish(
                task_id,
                "progress",
                {"stage": "extraction", "message": "姝ｅ湪鎻愬彇棰樼洰..."},
            )
            detection, problems = self.extraction.extract_problems(payload, asset)
            context.detection = detection
            context.problems = problems

            # 阶段 2：求解
            self.event_bus.publish(
                task_id, "progress", {"stage": "solving", "message": "姝ｅ湪瑙ｉ..."}
            )
            solutions = self.solving.generate_solutions(
                payload,
                problems,
                on_progress=lambda idx, total: self.event_bus.publish(
                    task_id,
                    "progress",
                    {"stage": "solving", "message": f"瑙ｉ涓?({idx}/{total})..."},
                ),
            )
            context.solutions = solutions

            # 阶段 3：打标
            self.event_bus.publish(
                task_id, "progress", {"stage": "tagging", "message": "姝ｅ湪鏍囨敞..."}
            )
            tags = self.tagging.generate_tags(payload, problems, solutions)
            context.tags = tags

            # 阶段 4：归档
            self.event_bus.publish(
                task_id,
                "progress",
                {"stage": "archiving", "message": "姝ｅ湪褰掓。..."},
            )
            self.archiving.archive_task(task_id, problems)

            # 保存结果
            self.repository.save_pipeline_result(task_id, None)  # type: ignore

            # 标记完成
            self.event_bus.publish(
                task_id, "progress", {"stage": "completed", "message": "处理完成"}
            )

            return context

        except Exception as e:
            logger.exception("Task processing failed: %s", e)
            self.event_bus.publish(
                task_id, "error", {"stage": "failed", "message": str(e)}
            )
            raise
