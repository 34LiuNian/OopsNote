"""OopsNote Core 数据模型。

所有模型独立于存储格式，方便迁移和版本管理。
JSON uuid (problem_id) 与 Obsidian 文件名 (日期-序号.md) 一一对应。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from oopsnote.content import (
    normalize_oopsmark,
    normalize_option_text,
    validate_oopsmark,
)


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
    DIAGRAM_GENERATING = "diagram_generating"
    DIAGRAM_RENDERING = "diagram_rendering"
    DIAGRAM_REVIEWING = "diagram_reviewing"


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


class RunPurpose(str, Enum):
    PROBLEM = "problem"
    DIAGRAM = "diagram"


class DiagramStatus(str, Enum):
    DETECTED = "detected"
    QUEUED = "queued"
    GENERATING = "generating"
    RENDERING = "rendering"
    REVIEWING = "reviewing"
    READY_TIKZ = "ready_tikz"
    READY_IMAGE = "ready_image"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DiagramRunMode(str, Enum):
    AUTO = "auto"
    CONTINUE = "continue"
    REBUILD = "rebuild"
    HUMAN = "human"


class DiagramRunStep(str, Enum):
    GENERATE = "generate"
    RENDER = "render"
    REVIEW = "review"


class DiagramSourceRegion(BaseModel):
    """Normalized source region reserved for a future layout-analysis owner."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "DiagramSourceRegion":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Diagram source region exceeds source bounds")
        return self


class DiagramCandidate(BaseModel):
    """One immutable TikZ proposal and the assets rendered from that source."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    ordinal: int = Field(ge=1)
    parent_candidate_id: Optional[str] = None
    source_kind: Literal["ai", "human", "legacy"] = "ai"
    tikz_source: str = Field(min_length=1)
    source_sha256: str = ""
    svg_path: Optional[str] = None
    pdf_path: Optional[str] = None
    png_path: Optional[str] = None
    renderer_profile_version: Optional[str] = None
    decision: Optional[Literal["accept", "revise", "keep_image"]] = None
    hard_errors: list[str] = Field(default_factory=list)
    soft_differences: list[str] = Field(default_factory=list)
    review_reason: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def populate_source_hash(self) -> "DiagramCandidate":
        digest = hashlib.sha256(self.tikz_source.encode("utf-8")).hexdigest()
        if self.source_sha256 and self.source_sha256 != digest:
            raise ValueError("Diagram candidate source_sha256 does not match tikz_source")
        self.source_sha256 = digest
        return self


class DiagramItem(BaseModel):
    """One printed diagram slot; a task currently creates one, the contract supports many."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    ordinal: int = Field(default=0, ge=0)
    source_asset_path: Optional[str] = None
    source_region: Optional[DiagramSourceRegion] = None
    fallback_image_path: Optional[str] = None
    image_tone: Literal["auto", "original"] = "auto"
    position: Literal["left", "right"] = "right"
    scale_percent: int = Field(default=100, ge=50, le=200)
    status: DiagramStatus = DiagramStatus.DETECTED
    selected_candidate_id: Optional[str] = None
    candidates: list[DiagramCandidate] = Field(default_factory=list)
    active_run_id: Optional[str] = None
    needs_review: bool = False
    last_error: Optional[str] = None
    last_error_code: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_candidates(self) -> "DiagramItem":
        ids = [candidate.id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Diagram candidate ids must be unique")
        ordinals = [candidate.ordinal for candidate in self.candidates]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("Diagram candidate ordinals must be unique")
        if self.selected_candidate_id and self.selected_candidate_id not in ids:
            raise ValueError("selected_candidate_id must reference a retained candidate")
        return self


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

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: Any) -> Any:
        # Legacy JSON may contain naive timestamps; persisted timestamps are UTC.
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @model_validator(mode="after")
    def validate_versioned_content(self) -> "Problem":
        if self.question_type == QuestionType.SINGLE_CHOICE and self.options:
            choice_answer = re.fullmatch(
                r"\s*(?:答案(?:为|是)?[:：]?\s*)?([A-H](?:[\s,，、/;；]*[A-H])*)\s*",
                self.answer,
                flags=re.IGNORECASE,
            )
            if choice_answer and len(re.findall(r"[A-H]", choice_answer.group(1), re.IGNORECASE)) > 1:
                raise ValueError("single-choice answer must contain exactly one option label")
        if self.content_format != ContentFormat.OOPSMARK_V1:
            return self
        # Normalize newlines before validation
        self.problem_text = normalize_oopsmark(self.problem_text)
        self.answer = normalize_oopsmark(self.answer)
        self.short_answer = normalize_oopsmark(self.short_answer)
        self.explanation = normalize_oopsmark(self.explanation)
        self.options = [normalize_option_text(o) for o in self.options]
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
    section_question_count: Optional[int] = Field(default=None, ge=1)


class OcrPrintedContext(BaseModel):
    """Printed identifiers observed by OCR, separate from user corrections."""

    printed_question_no: Optional[int] = Field(default=None, ge=1, le=999)
    printed_chapter: Optional[str] = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def normalize_chapter(self) -> "OcrPrintedContext":
        if self.printed_chapter is not None:
            self.printed_chapter = self.printed_chapter.strip() or None
        return self


class TaskRecord(BaseModel):
    """任务持久化记录。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str = ""
    status: TaskStatus = TaskStatus.PENDING
    problem: Optional[Problem] = None
    asset_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagram_items: list[DiagramItem] = Field(default_factory=list)
    ocr_context: Optional[OcrPrintedContext] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: Optional[str] = None
    last_error_code: Optional[str] = None
    revision_count: Optional[int] = Field(default=None, ge=0)
    last_revised_at: Optional[datetime] = None
    difficulty_coefficient_override: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
    )
    section_question_count: Optional[int] = Field(default=None, ge=1)
    stage: Optional[TaskStage] = None
    stage_message: Optional[str] = None
    active_run_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_diagram_metadata(cls, value: Any) -> Any:
        """Move the former singular metadata fields into the canonical item list."""
        if not isinstance(value, dict) or value.get("diagram_items"):
            return value
        metadata = value.get("metadata")
        if not isinstance(metadata, dict) or not metadata.get("diagram_detected"):
            return value
        legacy_keys = {
            "diagram_detected", "diagram_kind", "diagram_tikz_source", "diagram_svg",
            "diagram_image_path", "diagram_image_crop", "diagram_image_tone",
            "diagram_position", "diagram_scale_percent", "diagram_render_status",
            "diagram_error", "diagram_needs_review",
        }
        clean_metadata = {key: item for key, item in metadata.items() if key not in legacy_keys}
        kind = metadata.get("diagram_kind")
        source = str(metadata.get("diagram_tikz_source") or "").strip()
        candidates: list[dict[str, Any]] = []
        selected_candidate_id = None
        if kind == "tikz" and source:
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
            selected_candidate_id = f"legacy-{digest[:20]}"
            candidates.append({
                "id": selected_candidate_id,
                "ordinal": 1,
                "source_kind": "legacy",
                "tikz_source": source,
                "decision": "revise",
                "review_reason": "Legacy TikZ requires same-source SVG/PDF/PNG rendering",
            })
        crop = metadata.get("diagram_image_crop")
        item_digest = hashlib.sha256(
            f"{value.get('id', '')}\0{value.get('asset_path', '')}\0legacy-diagram-0".encode("utf-8")
        ).hexdigest()[:20]
        item = {
            "id": f"legacy-item-{item_digest}",
            "ordinal": 0,
            "source_asset_path": value.get("asset_path"),
            "source_region": crop if isinstance(crop, dict) else None,
            "fallback_image_path": metadata.get("diagram_image_path"),
            "image_tone": metadata.get("diagram_image_tone") or "auto",
            "position": metadata.get("diagram_position") or "right",
            "scale_percent": metadata.get("diagram_scale_percent") or 100,
            "status": (
                "needs_review" if selected_candidate_id else
                "ready_image" if kind == "image" and metadata.get("diagram_image_path") else
                "needs_review" if metadata.get("diagram_needs_review") else
                "detected"
            ),
            "selected_candidate_id": selected_candidate_id,
            "candidates": candidates,
            "needs_review": bool(metadata.get("diagram_needs_review") or selected_candidate_id),
            "last_error": metadata.get("diagram_error") or (
                "Legacy TikZ requires same-source rendering" if selected_candidate_id else None
            ),
        }
        return {**value, "metadata": clean_metadata, "diagram_items": [item]}

    def effective_question_no(self) -> Optional[str]:
        raw = self.metadata.get("question_no")
        if raw is None:
            raw = self.metadata.get("batch_question_no")
        if raw is None and self.ocr_context:
            raw = self.ocr_context.printed_question_no
        trace = self.metadata.get("trace")
        if raw is None and isinstance(trace, dict):
            raw = trace.get("question_no")
        value = str(raw or "").strip()
        return value or None

    def effective_chapter(self) -> Optional[str]:
        for raw in (
            self.metadata.get("chapter"),
            self.metadata.get("source_chapter"),
            self.ocr_context.printed_chapter if self.ocr_context else None,
        ):
            value = str(raw or "").strip()
            if value:
                return value
        return None


class StageRun(BaseModel):
    """A persisted observation of one AI pipeline stage."""

    stage: TaskStage
    status: StageStatus = StageStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    latency_ms: Optional[int] = None


class RunArtifact(BaseModel):
    """An immutable raw/parsed model-output observation for one managed run."""

    stage: TaskStage
    kind: Literal["ocr", "solver_candidate", "verifier_submission"]
    raw_output: str
    parsed_output: dict[str, Any]
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunValidationError(BaseModel):
    """An immutable record of a rejected managed-model output."""

    stage: TaskStage
    raw_output: str
    message: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SolutionCandidate(BaseModel):
    """A validated but uncommitted solution handed to an independent verifier."""

    problem: Problem
    review_reason: Literal["", "unreadable", "incomplete", "multiple_questions", "other"] = ""
    student_response_status: Literal["answered", "unanswered", "unknown"] = "unknown"
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskRun(BaseModel):
    """One managed AI process execution for a task."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    workspace_id: Optional[str] = None
    quota_reservation_id: Optional[str] = None
    purpose: RunPurpose = RunPurpose.PROBLEM
    priority: int = Field(default=0, ge=0, le=100)
    diagram_item_id: Optional[str] = None
    diagram_mode: Optional[DiagramRunMode] = None
    diagram_instruction: Optional[str] = Field(default=None, max_length=2000)
    diagram_max_candidates: Optional[int] = Field(default=None, ge=1, le=8)
    diagram_step: Optional[DiagramRunStep] = None
    diagram_candidate_id: Optional[str] = None
    attempt: int = 1
    status: RunStatus = RunStatus.QUEUED
    stage_runs: list[StageRun] = Field(default_factory=list)
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    log_path: Optional[str] = None
    backend: str = "pi"
    runtime_kind: Optional[str] = None
    runtime_version: Optional[str] = None
    worker_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    # Immutable, non-secret provider metadata selected at admission.  The
    # credential reference is opaque; secret material never enters a TaskRun.
    provider_profile_snapshot: Optional[dict[str, Any]] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_tokens: Optional[int] = None
    cost: Optional[float] = None
    stats_sessions: int = Field(default=0, ge=0)
    duration_ms: Optional[int] = None
    peak_memory_bytes: Optional[int] = Field(default=None, ge=0)
    rpc_log_path: Optional[str] = None
    retry_count: int = 0
    retry_of_run_id: Optional[str] = None
    retry_root_run_id: Optional[str] = None
    retryable: bool = False
    prompt_version: str = "unversioned"
    artifacts: list[RunArtifact] = Field(default_factory=list, max_length=3)
    validation_errors: list[RunValidationError] = Field(default_factory=list)
    solution_candidate: Optional[SolutionCandidate] = None
    verification_started_at: Optional[datetime] = None
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @model_validator(mode="after")
    def require_candidate_before_verification(self) -> "TaskRun":
        """Keep verification state impossible until solver output is durable."""
        if self.verification_started_at is not None and self.solution_candidate is None:
            raise ValueError("verification_started_at requires a solution_candidate")
        if self.purpose == RunPurpose.DIAGRAM:
            if not self.diagram_item_id or not self.diagram_mode or not self.diagram_max_candidates:
                raise ValueError("Diagram runs require item, mode, and candidate limit")
            if self.solution_candidate is not None or self.verification_started_at is not None:
                raise ValueError("Diagram runs cannot contain a problem solution candidate")
        return self


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


class BatchColumnLayout(BaseModel):
    """One document-wide fixed column layout for batch selection."""

    column_count: int = Field(default=1, ge=1, le=8)
    overlap_ratio: float = Field(default=0.5, ge=0, le=0.5)


class BatchSegmentPart(BaseModel):
    """One page-local projection of a document-space selection."""

    page_index: int = Field(ge=0)
    column_index: int = Field(default=0, ge=0)
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
    status: Literal["pending", "processing", "completed", "failed", "needs_review"] = "pending"
    review_reason: Optional[
        Literal["unreadable", "incomplete", "multiple_questions", "other"]
    ] = None
    review_previous_status: Optional[
        Literal["pending", "processing", "completed", "failed"]
    ] = None
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
        orders = sorted(part.order for part in self.parts)
        if orders != list(range(len(self.parts))):
            raise ValueError("Batch segment part orders must be unique and contiguous from zero")
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
    column_layout: BatchColumnLayout = Field(default_factory=BatchColumnLayout)
    excluded_page_indices: list[int] = Field(default_factory=list)
    segments: list[BatchSegment] = Field(default_factory=list)
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_excluded_pages(self) -> "BatchSessionRecord":
        self.excluded_page_indices = sorted(set(self.excluded_page_indices))
        if any(index < 0 or (self.page_count > 0 and index >= self.page_count) for index in self.excluded_page_indices):
            raise ValueError("Excluded page index is outside the source document")
        if self.page_count > 0 and len(self.excluded_page_indices) >= self.page_count:
            raise ValueError("Batch session must retain at least one page")
        excluded = set(self.excluded_page_indices)
        for segment in self.segments:
            previous_location: tuple[int, int] | None = None
            for part in sorted(segment.parts, key=lambda item: item.order):
                if self.page_count > 0 and part.page_index >= self.page_count:
                    raise ValueError("Batch segment part references unavailable page")
                if part.page_index in excluded:
                    raise ValueError("Batch segment part references an excluded page")
                if part.column_index >= self.column_layout.column_count:
                    raise ValueError("Batch segment part references unavailable column")
                location = (part.page_index, part.column_index)
                if previous_location is not None and location <= previous_location:
                    raise ValueError("Batch segment parts must follow document reading order")
                previous_location = location
        return self


class BatchSessionUpdateRequest(BaseModel):
    asset_path: Optional[str] = None
    filename: Optional[str] = Field(default=None, min_length=1, max_length=255)
    mime_type: Optional[str] = None
    page_count: Optional[int] = Field(default=None, ge=0)
    subject: Optional[str] = None
    notes: Optional[str] = None
    active_page: Optional[int] = Field(default=None, ge=0)
    crop_rect: Optional[BatchCropRect] = None
    crop_confirmed: Optional[bool] = None
    column_layout: Optional[BatchColumnLayout] = None
    excluded_page_indices: Optional[list[int]] = None
    segments: Optional[list[BatchSegment]] = None


class BatchProcessSegmentState(BaseModel):
    """Durable checkpoint for one segment in a batch-processing command."""

    segment_id: str
    question_no: Optional[int] = None
    status: Literal[
        "pending",
        "rendering",
        "asset_saved",
        "task_created",
        "processing",
        "completed",
        "failed",
    ] = "pending"
    asset_path: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    error: Optional[str] = None


class BatchProcessJob(BaseModel):
    """Recoverable manifest for the single-command batch pipeline."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    file_hash: str
    backend: str
    status: Literal["pending", "running", "submitted", "partial", "failed"] = "pending"
    segments: list[BatchProcessSegmentState] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


# ── 试卷草稿 ──────────────────────────────────────────

class PaperDraftItem(BaseModel):
    """A problem reference plus paper-local layout properties."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    problem_id: str
    question_type: str
    difficulty_coefficient: Optional[float] = Field(default=None, ge=0, le=1)
    points: Optional[float] = Field(default=None, ge=0)
    answer_space: Literal["compact", "standard", "large"] = "standard"


class PaperDraft(BaseModel):
    """A persistent composition that keeps Core problems as its only content source."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "未命名试卷"
    subject: str = "math"
    knowledge_tags: list[str] = Field(default_factory=list)
    knowledge_node_ids: list[str] = Field(default_factory=list)
    difficulty_preset: str = "medium"
    difficulty_distribution: dict[str, int] = Field(
        default_factory=lambda: {"easy": 50, "medium": 45, "hard": 5}
    )
    requested_counts: dict[str, int] = Field(default_factory=dict)
    items: list[PaperDraftItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaperDraftCreateRequest(BaseModel):
    title: str = "未命名试卷"
    subject: str = "math"
    knowledge_tags: list[str] = Field(default_factory=list)
    knowledge_node_ids: list[str] = Field(default_factory=list)
    difficulty_preset: str = "medium"
    difficulty_distribution: dict[str, int] = Field(
        default_factory=lambda: {"easy": 50, "medium": 45, "hard": 5}
    )
    requested_counts: dict[str, int] = Field(default_factory=dict)
    auto_select: bool = True


class PaperDraftUpdateRequest(BaseModel):
    title: Optional[str] = None
    knowledge_tags: Optional[list[str]] = None
    knowledge_node_ids: Optional[list[str]] = None
    difficulty_preset: Optional[str] = None
    difficulty_distribution: Optional[dict[str, int]] = None
    requested_counts: Optional[dict[str, int]] = None
    items: Optional[list[PaperDraftItem]] = None


# ── 搜索 ──────────────────────────────────────────────

class SearchQuery(BaseModel):
    tags: list[str] = Field(default_factory=list)
    subject: Optional[str] = None
    since: Optional[datetime] = None
    error_type: Optional[str] = None
    regex: Optional[str] = None
    limit: int = 50


class ProblemMergeRecord(BaseModel):
    """One explicit duplicate decision; source remains fully preserved."""

    source_problem_id: str
    target_problem_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VariationRequest(BaseModel):
    """Persisted generation constraints for a targeted derived problem."""

    parent_problem_id: str
    error_hypotheses: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    direction: str = "change_conditions"
    custom_request: str = Field(default="", max_length=2000)
    difficulty: Optional[str] = None
