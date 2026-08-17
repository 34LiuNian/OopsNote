"""REST-only request DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from oopsnote.core import BatchSessionUpdateRequest, TagDimension


class UploadRequest(BaseModel):
    subject: str = "auto"
    notes: str = ""
    question_no: str | None = None
    source: str | None = None
    question_type: str | None = None
    difficulty: str | None = None
    knowledge_tags: list[str] = Field(default_factory=list)
    error_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    image_base64: str
    filename: str
    mime_type: str = "image/png"
    batch_session_hash: str | None = None
    batch_segment_id: str | None = None
    batch_page_index: int | None = Field(default=None, ge=0)
    batch_question_no: int | None = Field(default=None, ge=1)


class TagInput(BaseModel):
    dimension: TagDimension
    value: str
    aliases: list[str] = Field(default_factory=list)
    subject: str | None = None


class TagRenameInput(BaseModel):
    value: str


class BatchSessionPatchRequest(BatchSessionUpdateRequest):
    expected_revision: int = Field(ge=0)


class BatchProcessRequest(BaseModel):
    expected_revision: int = Field(ge=0)


class BatchDeleteRequest(BaseModel):
    source: bool = False
    selection_records: bool = False
    tasks: bool = False


class PaperCompileItem(BaseModel):
    task_id: str
    problem_id: str


class PaperCompileRequest(BaseModel):
    items: list[PaperCompileItem] = Field(min_length=1, max_length=500)
    title: str = Field(default="试卷", min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=200)
    show_answers: bool = False
    diagram_scale_percent: int = Field(default=60, ge=25, le=200)


class PaperDraftCompileRequest(BaseModel):
    subtitle: str | None = Field(default=None, max_length=200)
    show_answers: bool = False
    diagram_scale_percent: int = Field(default=60, ge=25, le=200)


__all__ = [
    "BatchDeleteRequest",
    "BatchProcessRequest",
    "BatchSessionPatchRequest",
    "PaperCompileItem",
    "PaperCompileRequest",
    "PaperDraftCompileRequest",
    "TagInput",
    "TagRenameInput",
    "UploadRequest",
]
