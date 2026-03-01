"""
API request/response models for various endpoints.
"""

from __future__ import annotations

from typing import List, Optional, Dict

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .common import OptionItem


class UploadRequest(BaseModel):
    """Request to upload an image for processing."""

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
    """Request to compile LaTeX content."""

    content: str = Field(description="LaTeX document body content")
    title: Optional[str] = Field(default="LaTeX 测试", description="Document title")
    author: Optional[str] = Field(default="OopsNote", description="Document author")


class PaperItemRequest(BaseModel):
    """Request item for paper compilation."""

    task_id: str
    problem_id: str


class PaperCompileRequest(BaseModel):
    """Request to compile a paper from multiple problems."""

    items: List[PaperItemRequest]
    title: Optional[str] = Field(default="试卷", description="Paper title")
    show_answers: bool = Field(
        default=False, description="Whether to show answers in paper"
    )


class ChemfigRenderRequest(BaseModel):
    """Request to render chemfig structure."""

    content: str = Field(description="Chemfig content (with or without \\chemfig{...})")
    inline: bool = Field(default=False, description="Whether to render as inline math")


class OverrideProblemRequest(BaseModel):
    """Request to override problem details."""

    question_no: Optional[str] = None
    problem_text: Optional[str] = None
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
    """Request to retag a problem."""

    model: Optional[str] = Field(
        default=None, description="Optional model override for tagging"
    )
    force: bool = Field(default=False, description="Ignore locked_tags and force retag")


class ModelSummary(BaseModel):
    """Summary of an available model."""

    id: str
    provider: Optional[str] = None
    provider_type: Optional[str] = None


class ModelsResponse(BaseModel):
    """Response with available models."""

    items: List[ModelSummary]


class AgentModelsResponse(BaseModel):
    """Response with agent model configuration."""

    models: Dict[str, str]


class AgentModelsUpdateRequest(BaseModel):
    """Request to update agent model configuration."""

    models: Dict[str, str]


class AgentEnabledResponse(BaseModel):
    """Response with agent enabled status."""

    enabled: Dict[str, bool]


class AgentEnabledUpdateRequest(BaseModel):
    """Request to update agent enabled status."""

    enabled: Dict[str, bool]


class AgentThinkingResponse(BaseModel):
    """Response with agent thinking mode status."""

    thinking: Dict[str, bool]


class AgentThinkingUpdateRequest(BaseModel):
    """Request to update agent thinking mode status."""

    thinking: Dict[str, bool]
