"""
Problem and solution models.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import OptionItem
from ..config.subjects import DEFAULT_SUBJECT, VALID_SUBJECT_KEYS


class ProblemBlock(BaseModel):
    """Extracted problem block from OCR."""

    problem_id: str
    region_id: str
    subject: str = Field(
        default=DEFAULT_SUBJECT,
        description=f"Auto-detected subject: {', '.join(VALID_SUBJECT_KEYS)}",
    )
    question_no: Optional[str] = Field(
        default=None,
        description="User-provided problem identifier (can be alphanumeric); used for display only",
    )
    question_type: Optional[str] = Field(
        default=None, description="Optional manual question type label"
    )
    problem_text: str
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
    """Solution block for a problem."""

    problem_id: str
    answer: str
    explanation: str
    short_answer: Optional[str] = Field(
        default=None, description="Optional short-form answer for summary views"
    )


class TaggingResult(BaseModel):
    """Tagging result from AI agent."""

    # Backward compatible with previously persisted tasks that may include extra keys.
    model_config = ConfigDict(extra="ignore")

    problem_id: str
    knowledge_points: List[str]
    question_type: str
    skills: List[str]
    error_hypothesis: List[str]
    recommended_actions: List[str]


class ArchiveRecord(BaseModel):
    """Archive record for persisted problems."""

    task_id: str
    stored_problem_ids: List[str]
    timestamp: datetime
