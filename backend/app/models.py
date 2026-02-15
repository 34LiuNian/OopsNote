from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CropRegion(BaseModel):
    id: str
    bbox: List[float] = Field(
        ..., min_length=4, max_length=4, description="[x, y, width, height] normalized"
    )
    label: Literal["full", "partial", "noise"] = "full"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: List[float]):
        if any(coordinate < 0 or coordinate > 1 for coordinate in value):
            raise ValueError("bbox coordinates must be normalized between 0 and 1")
        return value


class DetectionOutput(BaseModel):
    action: Literal["multi", "single", "single-noise"]
    regions: List[CropRegion] = Field(default_factory=list)


class OptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Option key such as A/B/C/D")
    text: str = Field(description="Rendered option text, may contain LaTeX markup")
    latex_blocks: List[str] = Field(default_factory=list)

    @field_validator("key", "text")
    @classmethod
    def validate_non_empty(cls, value: str):
        trimmed = str(value).strip()
        if not trimmed:
            raise ValueError("Option key/text must be non-empty")
        return trimmed


class ProblemBlock(BaseModel):
    problem_id: str
    region_id: str
    question_no: Optional[str] = Field(
        default=None,
        description="User-provided problem identifier (can be alphanumeric); used for display only",
    )
    question_type: Optional[str] = Field(
        default=None, description="Optional manual question type label"
    )
    problem_text: str
    latex_blocks: List[str] = Field(default_factory=list)
    ocr_text: Optional[str] = Field(
        default=None, description="Raw OCR text before cleanup"
    )
    crop_image_url: Optional[str] = Field(
        default=None, description="URL or path of the cropped region"
    )
    locked_tags: bool = Field(
        default=False, description="If true, skip auto-retag unless forced"
    )
    media_notes: Optional[str] = None
    options: List[OptionItem] = Field(
        default_factory=list, description="Optional choice items"
    )
    source: Optional[str] = Field(
        default=None, description="Paper/exam source, e.g. 2024-XX-mock-exam"
    )
    knowledge_tags: List[str] = Field(
        default_factory=list,
        description="Manual knowledge-system tags for this problem",
    )
    error_tags: List[str] = Field(
        default_factory=list,
        description="Manual error-attribution tags for this problem",
    )
    user_tags: List[str] = Field(
        default_factory=list, description="Manual custom tags for this problem"
    )
    crop_bbox: Optional[List[float]] = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="[x, y, width, height] normalized coordinates copied from CropRegion",
    )


class SolutionBlock(BaseModel):
    problem_id: str
    answer: str
    explanation: str
    short_answer: Optional[str] = Field(
        default=None, description="Optional short-form answer for summary views"
    )


class TaggingResult(BaseModel):
    # Backward compatible with previously persisted tasks that may include extra keys.
    model_config = ConfigDict(extra="ignore")

    problem_id: str
    knowledge_points: List[str]
    question_type: str
    skills: List[str]
    error_hypothesis: List[str]
    recommended_actions: List[str]


class ArchiveRecord(BaseModel):
    task_id: str
    stored_problem_ids: List[str]
    timestamp: datetime


class AssetSource(str, Enum):
    UPLOAD = "upload"
    REMOTE = "remote"


class AssetMetadata(BaseModel):
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
    task: TaskRecord


class TaskSummary(BaseModel):
    id: str
    status: TaskStatus
    stage: Optional[str] = None
    stage_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    subject: str
    question_no: Optional[str] = None


class TasksResponse(BaseModel):
    items: List[TaskSummary]


class PipelineResult(BaseModel):
    detection: DetectionOutput
    problems: List[ProblemBlock]
    solutions: List[SolutionBlock]
    tags: List[TaggingResult]
    archive: ArchiveRecord


class ProblemSummary(BaseModel):
    """Flattened view of a single problem across all tasks, for library/list APIs."""

    task_id: str
    problem_id: str
    question_no: Optional[str] = None
    question_type: Optional[str] = None
    problem_text: str
    options: List[OptionItem] = Field(default_factory=list)
    subject: str
    grade: Optional[str] = None
    source: Optional[str] = None
    knowledge_points: List[str] = Field(default_factory=list)
    knowledge_tags: List[str] = Field(default_factory=list)
    error_tags: List[str] = Field(default_factory=list)
    user_tags: List[str] = Field(default_factory=list)


class ProblemsResponse(BaseModel):
    items: List[ProblemSummary]


class UploadRequest(BaseModel):
    image_url: Optional[HttpUrl] = None
    image_base64: Optional[str] = Field(
        default=None,
        description="Base64 encoded image, data URI prefix optional",
    )
    filename: Optional[str] = None
    mime_type: Optional[str] = Field(default="image/png")
    subject: str = Field(default="math")
    grade: Optional[str] = None
    notes: Optional[str] = None
    question_no: Optional[str] = None
    question_type: Optional[str] = None
    mock_problem_count: Optional[int] = Field(default=None, ge=1, le=8)
    difficulty: Optional[str] = None
    source: Optional[str] = None
    options: List[OptionItem] = Field(default_factory=list)
    knowledge_tags: List[str] = Field(default_factory=list)
    error_tags: List[str] = Field(default_factory=list)
    user_tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source(self) -> "UploadRequest":
        if not self.image_url and not self.image_base64:
            raise ValueError("Upload requires either image_url or image_base64")
        return self


class LatexCompileRequest(BaseModel):
    content: str = Field(description="LaTeX document body content")
    title: Optional[str] = Field(default="LaTeX 测试", description="Document title")
    author: Optional[str] = Field(default="OopsNote", description="Document author")


class PaperItemRequest(BaseModel):
    task_id: str
    problem_id: str


class PaperCompileRequest(BaseModel):
    items: List[PaperItemRequest]
    title: Optional[str] = Field(default="试卷", description="Paper title")
    subtitle: Optional[str] = Field(default=None, description="Paper subtitle")
    show_answers: bool = Field(
        default=False, description="Whether to show answers in paper"
    )


class ChemfigRenderRequest(BaseModel):
    content: str = Field(description="Chemfig content (with or without \\chemfig{...})")
    inline: bool = Field(default=False, description="Whether to render as inline math")


class OverrideProblemRequest(BaseModel):
    question_no: Optional[str] = None
    problem_text: Optional[str] = None
    latex_blocks: Optional[List[str]] = None
    options: Optional[List[OptionItem]] = None
    source: Optional[str] = None
    knowledge_tags: Optional[List[str]] = None
    error_tags: Optional[List[str]] = None
    user_tags: Optional[List[str]] = None
    knowledge_points: Optional[List[str]] = None
    question_type: Optional[str] = None
    skills: Optional[List[str]] = None
    error_hypothesis: Optional[List[str]] = None
    recommended_actions: Optional[List[str]] = None
    locked_tags: Optional[bool] = None
    crop_bbox: Optional[List[float]] = Field(default=None, min_length=4, max_length=4)
    crop_image_url: Optional[str] = None
    retag: bool = Field(
        default=False, description="If true, run tagger again after override"
    )


class RetagRequest(BaseModel):
    model: Optional[str] = Field(
        default=None, description="Optional model override for tagging"
    )
    force: bool = Field(default=False, description="Ignore locked_tags and force retag")


class ModelSummary(BaseModel):
    id: str
    provider: Optional[str] = None
    provider_type: Optional[str] = None


class ModelsResponse(BaseModel):
    items: List[ModelSummary]


class AgentModelsResponse(BaseModel):
    models: dict[str, str]


class AgentModelsUpdateRequest(BaseModel):
    models: dict[str, str]


class AgentEnabledResponse(BaseModel):
    enabled: dict[str, bool]


class AgentEnabledUpdateRequest(BaseModel):
    enabled: dict[str, bool]


class AgentThinkingResponse(BaseModel):
    thinking: dict[str, bool]


class AgentThinkingUpdateRequest(BaseModel):
    thinking: dict[str, bool]
