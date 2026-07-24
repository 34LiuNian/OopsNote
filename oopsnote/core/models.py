"""OopsNote Core 数据模型。

所有模型独立于存储格式，方便迁移和版本管理。
JSON uuid (problem_id) 与 Obsidian 文件名 (日期-序号.md) 一一对应。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from oopsnote.content import normalize_oopsmark, validate_oopsmark


# ── 枚举 ──────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStage(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    OCR = "ocr"
    SOLVING = "solving"
    VERIFYING = "verifying"
    TAGGING = "tagging"
    FINALIZING = "finalizing"
    SYNCING = "syncing"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class StageStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QuestionType(str, Enum):
    SINGLE_CHOICE = "单选题"
    MULTI_CHOICE = "多选题"
    FILL_BLANK = "填空题"
    SHORT_ANSWER = "解答题"


class TagDimension(str, Enum):
    KNOWLEDGE = "knowledge"
    ERROR = "error"
    META = "meta"
    CUSTOM = "custom"


class ContentFormat(str, Enum):
    """Versioned contract for rich problem content."""

    LEGACY_MARKDOWN_LATEX = "legacy-markdown-latex"
    OOPSMARK_V1 = "oopsmark-v1"


# ── 题目 ──────────────────────────────────────────────

class Problem(BaseModel):
    """一道题目。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str = ""                           # 数学/物理/化学
    question_type: QuestionType = QuestionType.SHORT_ANSWER
    content_format: ContentFormat = ContentFormat.LEGACY_MARKDOWN_LATEX
    problem_text: str = ""                      # Versioned by content_format
    options: list[str] = Field(default_factory=list)  # 选择题选项
    answer: str = ""
    short_answer: str = ""
    explanation: str = ""
    difficulty: Optional[str] = None
    has_diagram: bool = False
    knowledge_points: list[str] = Field(default_factory=list)
    error_hypothesis: list[str] = Field(default_factory=list)
    source: str = ""                            # 如 "2024-10 月考"
    source_page: Optional[int] = None           # PDF 页码
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_versioned_content(self) -> "Problem":
        if self.content_format != ContentFormat.OOPSMARK_V1:
            return self
        # Normalize newlines before validation
        self.problem_text = normalize_oopsmark(self.problem_text)
        self.answer = normalize_oopsmark(self.answer)
        self.short_answer = normalize_oopsmark(self.short_answer)
        self.explanation = normalize_oopsmark(self.explanation)
        self.options = [normalize_oopsmark(o) for o in self.options]
        # Validate
        fields = {
            "problem_text": self.problem_text,
            "answer": self.answer,
            "short_answer": self.short_answer,
            "explanation": self.explanation,
            **{f"options[{index}]": option for index, option in enumerate(self.options)},
        }
        for field_name, content in fields.items():
            issues = validate_oopsmark(content)
            if issues:
                issue = issues[0]
                raise ValueError(f"{field_name}:{issue.line} [{issue.code}] {issue.message}")
        return self


# ── 任务 ──────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    """前端/CLI/MCP 创建任务时的请求体。"""

    subject: str = ""
    asset_base64: Optional[str] = None          # 图片 base64
    asset_path: Optional[str] = None            # 本地 PDF/图片路径
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    """任务持久化记录。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str = ""
    status: TaskStatus = TaskStatus.PENDING
    problem: Optional[Problem] = None
    asset_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: Optional[str] = None
    stage: Optional[TaskStage] = None
    stage_message: Optional[str] = None
    active_run_id: Optional[str] = None


class StageRun(BaseModel):
    """A persisted observation of one AI pipeline stage."""

    stage: TaskStage
    status: StageStatus = StageStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    latency_ms: Optional[int] = None


class TaskRun(BaseModel):
    """One managed AI process execution for a task."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    attempt: int = 1
    status: RunStatus = RunStatus.QUEUED
    stage_runs: list[StageRun] = Field(default_factory=list)
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    log_path: Optional[str] = None
    backend: str = "hermes"
    runtime_kind: Optional[str] = None
    runtime_version: Optional[str] = None
    worker_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_tokens: Optional[int] = None
    cost: Optional[float] = None
    duration_ms: Optional[int] = None
    rpc_log_path: Optional[str] = None
    retry_count: int = 0
    retryable: bool = False
    prompt_version: str = "orchestrator-v3"
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ── 批量扫描会话 ────────────────────────────────────────

class BatchSegmentContinuation(BaseModel):
    """同一道题在紧邻下一页中的延续裁剪区域。"""

    page_index: int = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class BatchCropRect(BaseModel):
    """One normalized crop applied proportionally to every page in a PDF."""

    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(default=1, gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "BatchCropRect":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Batch crop rectangle exceeds page bounds")
        return self


class BatchSegmentPart(BaseModel):
    """One page-local projection of a document-space selection."""

    page_index: int = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "BatchSegmentPart":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Batch segment part exceeds page bounds")
        return self


class BatchSegment(BaseModel):
    """A selection persisted as an ordered list of page-local parts."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    parts: list[BatchSegmentPart] = Field(default_factory=list)
    # Legacy fields remain readable while old sessions migrate to parts[].
    page_index: Optional[int] = Field(default=None, ge=0)
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, gt=0, le=1)
    height: Optional[float] = Field(default=None, gt=0, le=1)
    continuation: Optional[BatchSegmentContinuation] = None
    question_no: Optional[int] = Field(default=None, ge=1)
    status: str = "pending"
    review_reason: Optional[str] = None
    review_previous_status: Optional[str] = None
    review_resolved: bool = False
    task_id: Optional[str] = None
    problem_ids: list[str] = Field(default_factory=list)
    error: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_parts(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("parts"):
            return value
        required = ("page_index", "x", "y", "width", "height")
        if not all(value.get(key) is not None for key in required):
            return value
        parts = [{
            "page_index": value["page_index"],
            "x": value["x"],
            "y": value["y"],
            "width": value["width"],
            "height": value["height"],
            "order": 0,
        }]
        continuation = value.get("continuation")
        if continuation:
            parts.append({**continuation, "order": 1})
        return {**value, "parts": parts}

    @model_validator(mode="after")
    def validate_parts(self) -> "BatchSegment":
        if not self.parts:
            raise ValueError("Batch segment requires at least one part")
        return self


class BatchSessionRecord(BaseModel):
    """按原始文件 SHA-256 去重的 Web 手动分割会话。"""

    file_hash: str
    filename: str
    mime_type: str = "application/pdf"
    asset_path: str
    page_count: int = 0
    subject: str = "auto"
    notes: str = ""
    active_page: int = 0
    crop_rect: BatchCropRect = Field(default_factory=BatchCropRect)
    crop_confirmed: bool = False
    segments: list[BatchSegment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BatchSessionUpdateRequest(BaseModel):
    page_count: Optional[int] = Field(default=None, ge=0)
    subject: Optional[str] = None
    notes: Optional[str] = None
    active_page: Optional[int] = Field(default=None, ge=0)
    crop_rect: Optional[BatchCropRect] = None
    crop_confirmed: Optional[bool] = None
    segments: Optional[list[BatchSegment]] = None


# ── 标签 ──────────────────────────────────────────────

class TagItem(BaseModel):
    """标签存储元数据。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    dimension: TagDimension = TagDimension.KNOWLEDGE
    value: str
    aliases: list[str] = Field(default_factory=list)
    subject: Optional[str] = None
    chapter: Optional[str] = None
    ref_count: int = 0
    source: str = "user"                        # "builtin" | "user"
    source_id: Optional[str] = None
    source_ids: list[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    path: list[str] = Field(default_factory=list)
    paths: list[list[str]] = Field(default_factory=list)
    depth: Optional[int] = None
    scope: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    is_leaf: Optional[bool] = None


class TagCreateRequest(BaseModel):
    dimension: TagDimension
    value: str
    aliases: list[str] = Field(default_factory=list)
    subject: Optional[str] = None


class TagsResponse(BaseModel):
    items: list[TagItem]


# ── 搜索 ──────────────────────────────────────────────

class SearchQuery(BaseModel):
    tags: list[str] = Field(default_factory=list)
    subject: Optional[str] = None
    since: Optional[str] = None
    error_type: Optional[str] = None
    regex: Optional[str] = None
    limit: int = 50
