"""依赖注入与接口契约的 Protocol 定义。

本模块定义抽象接口（protocol），用于落实良好代码中的接口原则：
- 职责分离：接口只暴露必要能力
- 稳定性：接口保持稳定、低频变更
- 契约化：类型、参数、返回值清晰
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from .models import (
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    TaskCreateRequest,
    TaskRecord,
    AssetMetadata,
    DetectionOutput,
    ArchiveRecord,
    PipelineResult,
)


@runtime_checkable
class AIClient(Protocol):
    """AI/LLM 客户端实现协议。

    该接口使业务逻辑可在不改动调用方的情况下切换不同 LLM 供应商。
    """

    model: str

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """执行结构化对话补全。"""

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """执行带图片输入的结构化对话补全。"""


@runtime_checkable
class Extractor(Protocol):
    """图片题目提取协议。"""

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
    ) -> list[ProblemBlock]:
        """从上传图片中提取题目。"""


@runtime_checkable
class Solver(Protocol):
    """题目求解协议。"""

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
    ) -> list[SolutionBlock]:
        """为已提取题目生成解答。"""


@runtime_checkable
class Tagger(Protocol):
    """题目打标协议。"""

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        solutions: Iterable[SolutionBlock],
    ) -> list[TaggingResult]:
        """为已解答题目生成标签。"""


@runtime_checkable
class Archiver(Protocol):
    """题目处理归档协议。"""

    def run(
        self,
        task_id: str,
        problems: Iterable[ProblemBlock],
    ) -> ArchiveRecord:
        """归档已处理题目。"""


@runtime_checkable
class TasksServiceLike(Protocol):
    """任务服务协议。"""

    def process_task(self, task_id: str, background: bool = False) -> Any:
        """通过 AI 流水线处理任务。"""


@runtime_checkable
class Repository(Protocol):
    """任务持久化协议。"""

    def create(self, payload: TaskCreateRequest, asset: AssetMetadata | None = None) -> TaskRecord:
        """创建新任务记录。"""

    def get(self, task_id: str) -> TaskRecord:
        """按 ID 获取任务。"""

    def update_task(self, task: TaskRecord) -> TaskRecord:
        """更新已有任务。"""

    def list_all(self) -> dict[str, TaskRecord]:
        """列出全部任务。"""

    def list_tasks(
        self,
        status: str | None = None,
        active_only: bool = False,
        subject: str | None = None,
    ) -> list[TaskRecord]:
        """按可选条件筛选任务列表。"""

    def get_task(self, task_id: str) -> TaskRecord:
        """按 ID 获取任务（旧别名）。"""

    def save_pipeline_result(
        self,
        task_id: str,
        result: PipelineResult,
    ) -> TaskRecord:
        """保存流水线处理结果。"""


@runtime_checkable
class EventBus(Protocol):
    """事件发布与订阅协议。"""

    def publish(
        self,
        task_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """发布任务事件。"""

    def subscribe(self, task_id: str) -> Iterable[dict[str, Any]]:
        """订阅任务事件。"""
