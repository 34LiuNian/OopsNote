"""任务相关模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .common import AssetSource, DetectionOutput, OptionItem, TaskStatus
from .problem import ProblemBlock, SolutionBlock, TaggingResult, ArchiveRecord


class AssetMetadata(BaseModel):
    """上传图片的资源元数据。"""

    # 兼容旧版持久化任务中可能存在的额外字段。
    model_config = ConfigDict(extra="ignore")

    asset_id: Optional[str] = None
    source: Optional[AssetSource] = None
    original_reference: Optional[str] = None
    path: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: datetime


class TaskCreateRequest(BaseModel):
    """创建新任务请求。"""

    image_url: HttpUrl
    subject: str = Field(
        default="auto",
        description="下游 Agent 使用的学科标签（`auto` 表示自动识别）",
    )
    grade: Optional[str] = Field(
        default=None, description="年级或难度提示")
    notes: Optional[str] = Field(
        default=None, description="自由文本提示，如多题线索"
    )
    question_no: Optional[str] = Field(
        default=None,
        description="用户提供的题号标识（可含字母数字）。",  # noqa: E501
    )
    question_type: Optional[str] = Field(
        default=None, description="可选的手动题型标签"
    )
    mock_problem_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=8,
        description="演示用途：覆盖检测器输出指定题目数量",
    )
    difficulty: Optional[str] = Field(
        default=None, description="用于排序的分数比例 a/b"
    )
    source: Optional[str] = Field(
        default=None, description="可选：试卷/考试来源标签"
    )
    options: List[OptionItem] = Field(
        default_factory=list, description="可选：手动填写的选项"
    )
    knowledge_tags: List[str] = Field(
        default_factory=list, description="手动知识体系标签"
    )
    error_tags: List[str] = Field(
        default_factory=list, description="手动错因归因标签"
    )
    user_tags: List[str] = Field(default_factory=list)


class TaskRecord(BaseModel):
    """包含完整信息的任务记录。"""

    id: str
    payload: TaskCreateRequest
    asset: Optional[AssetMetadata] = None
    status: TaskStatus = TaskStatus.PENDING
    stage: Optional[str] = Field(
        default=None, description="粗粒度进度阶段标识"
    )
    stage_message: Optional[str] = Field(
        default=None, description="面向用户的进度文本"
    )
    created_at: datetime
    updated_at: datetime
    last_error: Optional[str] = None
    detection: Optional[DetectionOutput] = None
    problems: List[ProblemBlock] = Field(default_factory=list)
    solutions: List[SolutionBlock] = Field(default_factory=list)
    tags: List[TaggingResult] = Field(default_factory=list)
    archive_record: Optional[ArchiveRecord] = None


class TaskResponse(BaseModel):
    """单任务响应。"""

    task: TaskRecord


class TaskSummary(BaseModel):
    """任务列表中的摘要视图。"""

    id: str
    status: TaskStatus
    stage: Optional[str] = None
    stage_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    subject: str
    question_no: Optional[str] = None
    asset: Optional[dict] = Field(
        default=None,
        description="缩略图展示用简化资源信息（asset_id、path、mime_type）",
    )


class TasksResponse(BaseModel):
    """任务列表响应。"""

    items: List[TaskSummary]
