"""应用服务层：位于 API 与领域层之间的编排层。

本模块提供面向用例的服务，通过协调领域服务来完成完整业务流程，
并遵循以下接口原则：
- 输入输出契约清晰
- 接口稳定、低频变更
- 与 API 层、领域层职责分离
"""

from __future__ import annotations


import logging

from datetime import datetime, timezone

from uuid import uuid4


from .models import (
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    UploadRequest,
    AssetMetadata,
    AssetSource,
)

from .protocols import Repository, EventBus

from .domain import (
    TaskProcessingService,
)

logger = logging.getLogger(__name__)


class ApplicationService:
    """应用层主服务，负责协调各类用例。

    主要职责：
    - 协调领域服务实现具体业务用例
    - 管理事务边界
    - 处理横切关注点（日志、事件）
    - 在 API 模型与领域模型之间做转换
    """

    def __init__(
        self,
        repository: Repository,
        event_bus: EventBus,
        processing: TaskProcessingService,
    ) -> None:

        self.repository = repository

        self.event_bus = event_bus

        self.processing = processing

    def create_task(self, payload: TaskCreateRequest) -> TaskRecord:
        """创建新任务。

        该用例只负责持久化任务，不触发处理流程。

        Args:
            payload: 任务创建请求

        Returns:
            创建后的任务记录
        """

        task_id = uuid4().hex

        now = datetime.now(timezone.utc)

        task = self.repository.create(payload)

        logger.info("Task created: %s", task_id)

        return task

    def upload_task(
        self, upload: UploadRequest, auto_process: bool = True
    ) -> TaskRecord:
        """处理上传并创建任务。

        执行步骤：
        1. 将上传请求转换为任务创建请求
        2. 创建任务记录
        3. 按需立即触发处理

        Args:
            upload: 含图片数据的上传请求
            auto_process: 是否立即开始处理

        Returns:
            创建后的任务记录
        """

        # 将上传请求转换为任务创建载荷
        from pydantic import HttpUrl, ValidationError

        if upload.image_url is None:
            raise ValueError("upload.image_url is required")
        try:
            http_url = HttpUrl(str(upload.image_url))
        except (ValidationError, ValueError) as exc:
            raise ValueError("Invalid upload.image_url") from exc
        
        payload = TaskCreateRequest(
            image_url=http_url,
            subject=upload.subject,
            grade=upload.grade,
            notes=upload.notes,
            question_no=upload.question_no,
            question_type=upload.question_type,
            mock_problem_count=upload.mock_problem_count,
            difficulty=upload.difficulty,
            source=upload.source,
            knowledge_tags=upload.knowledge_tags,
            error_tags=upload.error_tags,
            user_tags=upload.user_tags,
        )

        # 创建任务

        task = self.create_task(payload)

        # 保存资源元数据

        asset = AssetMetadata(
            asset_id=uuid4().hex,
            source=AssetSource.UPLOAD if upload.image_base64 else AssetSource.REMOTE,
            original_reference=upload.filename or str(upload.image_url),
            mime_type=upload.mime_type,
            created_at=datetime.now(timezone.utc),
        )

        task.asset = asset

        self.repository.update_task(task)

        # 按需自动触发处理

        if auto_process:

            self.process_task(task.id)

        return task

    def process_task(self, task_id: str, background: bool = False) -> TaskRecord:  # pylint: disable=unused-argument
        """通过 AI 流水线处理任务。

        执行步骤：
        1. 读取任务
        2. 执行处理流水线
        3. 更新任务状态

        Args:
            task_id: 任务 ID
            background: 是否后台执行（当前未实现）

        Returns:
            更新后的任务记录
        """

        task = self.repository.get_task(task_id)

        if task.status not in (TaskStatus.PENDING, TaskStatus.FAILED):

            raise ValueError(f"Cannot process task in status: {task.status}")

        try:

            # 执行流水线

            context = self.processing.process_task(
                task_id=task_id,
                payload=task.payload,
                asset=task.asset,
            )

            # 将处理结果回写到任务

            task.status = TaskStatus.COMPLETED

            task.detection = context.detection

            task.problems = context.problems

            task.solutions = context.solutions

            task.tags = context.tags

            task.updated_at = datetime.now(timezone.utc)

            self.repository.update_task(task)

            logger.info("Task completed: %s", task_id)

            return task

        except Exception as e:

            task.status = TaskStatus.FAILED

            task.last_error = str(e)

            task.updated_at = datetime.now(timezone.utc)

            self.repository.update_task(task)

            logger.error("Task failed: %s - %s", task_id, e)

            raise

    def get_task(self, task_id: str) -> TaskRecord:
        """按 ID 获取任务。

        Args:
            task_id: 任务 ID

        Returns:
            任务记录
        """

        return self.repository.get_task(task_id)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        active_only: bool = False,
        subject: str | None = None,
    ) -> list[TaskRecord]:
        """按条件筛选任务列表。

        Args:
            status: 按状态筛选
            active_only: 仅返回 `PENDING/PROCESSING` 任务
            subject: 按学科筛选

        Returns:
            任务记录列表
        """

        return self.repository.list_tasks(
            status=status.value if status else None,
            active_only=active_only,
            subject=subject,
        )

    def cancel_task(self, task_id: str) -> TaskRecord:
        """取消任务。

        Args:
            task_id: 任务 ID

        Returns:
            更新后的任务记录
        """

        task = self.repository.get_task(task_id)

        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):

            raise ValueError(f"Cannot cancel task in status: {task.status}")

        task.status = TaskStatus.CANCELLED

        task.updated_at = datetime.now(timezone.utc)

        self.repository.update_task(task)

        self.event_bus.publish(
            task_id, "cancelled", {"stage": "cancelled", "message": "任务已取消"}
        )

        logger.info("Task cancelled: %s", task_id)

        return task
