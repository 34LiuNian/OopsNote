"""OopsNote Core 数据模型。

所有模型独立于存储格式，方便迁移和版本管理。
JSON uuid (problem_id) 与 Obsidian 文件名 (日期-序号.md) 一一对应。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── 枚举 ──────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
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


# ── 题目 ──────────────────────────────────────────────

class Problem(BaseModel):
    """一道题目。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str = ""                           # 数学/物理/化学
    question_type: QuestionType = QuestionType.SHORT_ANSWER
    problem_text: str = ""                      # Markdown + LaTeX
    options: list[str] = Field(default_factory=list)  # 选择题选项
    answer: str = ""
    explanation: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    error_hypothesis: list[str] = Field(default_factory=list)
    source: str = ""                            # 如 "2024-10 月考"
    source_page: Optional[int] = None           # PDF 页码
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 任务 ──────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    """前端/CLI 创建任务时的请求体。"""

    subject: str = ""
    asset_base64: Optional[str] = None          # 图片 base64
    asset_path: Optional[str] = None            # 本地 PDF 路径
    tags: list[str] = Field(default_factory=list)


class TaskRecord(BaseModel):
    """任务持久化记录。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str = ""
    status: TaskStatus = TaskStatus.PENDING
    problems: list[Problem] = Field(default_factory=list)
    asset_path: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: Optional[str] = None


# ── 标签 ──────────────────────────────────────────────

class TagItem(BaseModel):
    """标签存储元数据。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    dimension: TagDimension = TagDimension.KNOWLEDGE
    value: str
    aliases: list[str] = Field(default_factory=list)
    subject: Optional[str] = None
    ref_count: int = 0
    source: str = "user"                        # "builtin" | "user"


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
