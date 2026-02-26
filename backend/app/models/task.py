"""
Task-related models.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .common import AssetSource, DetectionOutput, OptionItem, TaskStatus
from .problem import ProblemBlock, SolutionBlock, TaggingResult, ArchiveRecord


class AssetMetadata(BaseModel):
    """Asset metadata for uploaded images."""
    # Backward compatible with previously persisted tasks that may include extra keys.
    model_config = ConfigDict(extra="ignore")

    asset_id: Optional[str] = None
    source: Optional[AssetSource] = None
    original_reference: Optional[str] = None
    path: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: datetime


class TaskCreateRequest(BaseModel):
    """Request to create a new task."""
    image_url: HttpUrl
    subject: str = Field(
        default="math", description="Subject tag for downstream agents"
    )
    grade: Optional[str] = Field(default=None, description="Grade or difficulty hint")
    notes: Optional[str] = Field(
        default=None, description="Free-form hints such as multi-problem cues"
    )
    question_no: Optional[str] = Field(
        default=None,
        description="User-provided problem identifier (alphanumeric). Stored for display; internal problem_id uses UUID",
    )
    question_type: Optional[str] = Field(
        default=None, description="Optional manual question type label"
    )
    mock_problem_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=8,
        description="For demos: override detector to emit specific count",
    )
    difficulty: Optional[str] = Field(
        default=None, description="Score ratio a/b used for ordering"
    )
    source: Optional[str] = Field(
        default=None, description="Optional paper/exam source label"
    )
    options: List[OptionItem] = Field(
        default_factory=list, description="Optional manual choice items"
    )
    knowledge_tags: List[str] = Field(
        default_factory=list, description="Manual knowledge-system tags"
    )
    error_tags: List[str] = Field(
        default_factory=list, description="Manual error-attribution tags"
    )
    user_tags: List[str] = Field(default_factory=list)


class TaskRecord(BaseModel):
    """Task record with full details."""
    id: str
    payload: TaskCreateRequest
    asset: Optional[AssetMetadata] = None
    status: TaskStatus = TaskStatus.PENDING
    stage: Optional[str] = Field(
        default=None, description="Coarse progress stage identifier"
    )
    stage_message: Optional[str] = Field(
        default=None, description="Human-readable progress message"
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
    """Response with single task."""
    task: TaskRecord


class TaskSummary(BaseModel):
    """Summary view of a task for list views."""
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
        description="Simplified asset info for thumbnail display (asset_id, path, mime_type)"
    )


class TasksResponse(BaseModel):
    """Response with task list."""
    items: List[TaskSummary]
