"""
Common types and base classes for models module.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(str, Enum):
    """Task lifecycle status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssetSource(str, Enum):
    """Asset source type."""

    UPLOAD = "upload"
    REMOTE = "remote"


class CropRegion(BaseModel):
    """Crop region with normalized bounding box."""

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
    """Multi-problem detection output."""

    action: Literal["multi", "single", "single-noise"]
    regions: List[CropRegion] = Field(default_factory=list)


class OptionItem(BaseModel):
    """Multiple choice option item."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Option key such as A/B/C/D")
    text: str = Field(description="Rendered option text, may contain LaTeX markup")

    @field_validator("key", "text")
    @classmethod
    def validate_non_empty(cls, value: str):
        trimmed = str(value).strip()
        if not trimmed:
            raise ValueError("Option key/text must be non-empty")
        return trimmed
